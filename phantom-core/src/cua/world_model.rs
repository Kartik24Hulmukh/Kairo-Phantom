// phantom-core/src/cua/world_model.rs
//
// Persistent, versioned UIA tree representation (World Model)
// ─────────────────────────────────────────────────────────────────────────────

use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use super::WindowRect;

// Telemetry counters
pub static VLM_INVOCATIONS: AtomicUsize = AtomicUsize::new(0);
pub static TOTAL_ACTIONS: AtomicUsize = AtomicUsize::new(0);

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UiNode {
    pub runtime_id: Vec<i32>,
    pub control_type: i32,
    pub name: String,
    pub bbox: Option<WindowRect>,
    pub value_hash: u64,
    pub children: Vec<UiNode>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UiDelta {
    pub added: Vec<UiNode>,
    pub removed: Vec<Vec<i32>>,
    pub value_changed: Vec<(Vec<i32>, u64)>,
}

#[derive(Debug, Clone, Default)]
pub struct AppWorldModel {
    pub root: Option<UiNode>,
}

// Global cached world models keyed by "hwnd"
pub static GLOBAL_WORLD_MODEL: Lazy<Mutex<HashMap<isize, AppWorldModel>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

/// Computes a hash of the text value.
pub fn compute_hash(s: &str) -> u64 {
    use rustc_hash::FxHasher;
    use std::hash::Hasher;
    let mut hasher = FxHasher::default();
    hasher.write(s.as_bytes());
    hasher.finish()
}

/// Recursively traverses a UIA element and builds a UiNode tree.
#[cfg(target_os = "windows")]
pub fn build_tree(element: &uiautomation::core::UIElement, depth: usize) -> Result<UiNode, String> {
    if depth > 8 {
        return Err("Max depth reached".to_string());
    }

    let runtime_id = element.get_runtime_id().map_err(|e| e.to_string())?;
    let control_type = element.get_control_type().map_err(|e| e.to_string())?;
    let name = element.get_name().unwrap_or_default();

    let bbox = if let Ok(rect) = element.get_bounding_rectangle() {
        Some(WindowRect {
            left: rect.get_left(),
            top: rect.get_top(),
            right: rect.get_left() + rect.get_width(),
            bottom: rect.get_top() + rect.get_height(),
        })
    } else {
        None
    };

    let mut value_str = String::new();
    if let Ok(pat) = element.get_pattern::<uiautomation::patterns::UIValuePattern>() {
        if let Ok(val) = pat.get_value() {
            value_str = val;
        }
    } else if let Ok(pat) = element.get_pattern::<uiautomation::patterns::UITextPattern>() {
        if let Ok(range) = pat.get_document_range() {
            if let Ok(text) = range.get_text(-1) {
                value_str = text;
            }
        }
    }

    let value_hash = compute_hash(&value_str);

    let mut children = Vec::new();
    if depth < 8 {
        if let Ok(automation) = uiautomation::core::UIAutomation::new() {
            if let Ok(cond) = automation.create_true_condition() {
                if let Ok(elems) = element.find_all(uiautomation::types::TreeScope::Children, &cond)
                {
                    for elem in &elems {
                        if let Ok(child_node) = build_tree(elem, depth + 1) {
                            children.push(child_node);
                        }
                    }
                }
            }
        }
    }

    Ok(UiNode {
        runtime_id,
        control_type: control_type as i32,
        name,
        bbox,
        value_hash,
        children,
    })
}

/// Stub for non-Windows targets.
#[cfg(not(target_os = "windows"))]
pub fn build_tree(_element: &(), _depth: usize) -> Result<UiNode, String> {
    Err("UIA only supported on Windows".to_string())
}

/// Recursively diffs two trees.
pub fn diff_trees(old: &UiNode, new: &UiNode, delta: &mut UiDelta) {
    if old.runtime_id == new.runtime_id {
        if old.value_hash != new.value_hash {
            delta
                .value_changed
                .push((new.runtime_id.clone(), new.value_hash));
        }

        let mut old_children_map: HashMap<Vec<i32>, &UiNode> = old
            .children
            .iter()
            .map(|c| (c.runtime_id.clone(), c))
            .collect();

        for new_child in &new.children {
            if let Some(old_child) = old_children_map.remove(&new_child.runtime_id) {
                diff_trees(old_child, new_child, delta);
            } else {
                delta.added.push(new_child.clone());
            }
        }

        for (old_id, _) in old_children_map {
            delta.removed.push(old_id);
        }
    }
}

/// Recursively searches for an element in the tree matching the target name.
pub fn find_element_in_tree(node: &UiNode, name: &str) -> Option<UiNode> {
    if node.name.to_lowercase().contains(&name.to_lowercase()) {
        return Some(node.clone());
    }
    for child in &node.children {
        if let Some(found) = find_element_in_tree(child, name) {
            return Some(found);
        }
    }
    None
}

/// Gets the vertical scroll offset from scroll pattern if available.
#[cfg(target_os = "windows")]
pub fn get_vertical_scroll_offset(element: &uiautomation::core::UIElement) -> f64 {
    if let Ok(pat) = element.get_pattern::<uiautomation::patterns::UIScrollPattern>() {
        if let Ok(val) = pat.get_vertical_scroll_percent() {
            return val;
        }
    }
    0.0
}

#[cfg(not(target_os = "windows"))]
pub fn get_vertical_scroll_offset(_element: &()) -> f64 {
    0.0
}

/// Telemetry logging: returns vlm_call_rate as float.
pub fn get_vlm_call_rate() -> f32 {
    let total = TOTAL_ACTIONS.load(Ordering::SeqCst);
    if total == 0 {
        0.0
    } else {
        VLM_INVOCATIONS.load(Ordering::SeqCst) as f32 / total as f32
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_hash_deterministic() {
        let input = "Kairo Hashing";
        let h1 = compute_hash(input);
        let h2 = compute_hash(input);
        assert_eq!(h1, h2);
    }
}
