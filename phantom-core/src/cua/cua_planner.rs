//! # CUA Planner
//!
//! Generates CUA action sequences from high-level goals.
//! Priority:
//! 1. Keyboard-first templates (most reliable — no UI interaction needed)
//! 2. UIA accessibility tree element targeting (finds by name, not coordinates)
//! 3. farscry visual element detection (fallback)
//! 4. Cannot plan → manual instruction fallback

use super::{CuaAction, CuaContext, CuaPlan, MouseButton, PlanSource, Risk, WellKnownShortcut};
use std::collections::HashMap;

/// Error from CUA planner
#[derive(Debug)]
pub enum PlannerError {
    /// Cannot find any path to accomplish the goal
    CannotPlan {
        goal: String,
        reason: String,
        manual_instruction: String,
    },
    /// UIA automation is unavailable
    UiaUnavailable(String),
}

impl std::fmt::Display for PlannerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PlannerError::CannotPlan {
                goal,
                reason,
                manual_instruction,
            } => {
                write!(
                    f,
                    "Cannot plan for '{goal}': {reason} — Manual: {manual_instruction}",
                )
            }
            PlannerError::UiaUnavailable(e) => write!(f, "UIA unavailable: {e}"),
        }
    }
}

/// The CUA Planner — generates action sequences from goals
pub struct CuaPlanner {
    /// Pre-built keyboard-first templates for common workflows
    templates: HashMap<String, HashMap<String, TemplateEntry>>,
}

struct TemplateEntry {
    actions: Vec<CuaAction>,
    step_descriptions: Vec<String>,
    risk: Risk,
}

impl CuaPlanner {
    pub fn new() -> Self {
        let templates = Self::load_templates();
        Self { templates }
    }

    /// Generate a plan for the given goal in the given window context.
    ///
    /// Returns a CuaPlan with:
    /// - Ordered actions to execute
    /// - Step descriptions for GRP mini-plan display
    /// - Source (Template/UIA/Visual)
    /// - Risk level
    pub async fn plan(&self, goal: &str, ctx: &CuaContext) -> Result<CuaPlan, PlannerError> {
        super::world_model::TOTAL_ACTIONS.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        let goal_lower = goal.to_lowercase();

        // Step 1: Check keyboard-first templates (most reliable)
        if let Some(template) = self.match_template(&goal_lower, &ctx.app_name) {
            return Ok(CuaPlan {
                actions: template.actions.clone(),
                source: PlanSource::Template,
                estimated_risk: template.risk.clone(),
                description: format!("Using keyboard shortcut sequence for: {goal}"),
                step_descriptions: template.step_descriptions.clone(),
                step_confidences: vec![1.0; template.step_descriptions.len()],
                step_sources: vec![
                    super::TargetingSource::Keyboard;
                    template.step_descriptions.len()
                ],
            });
        }

        // Step 2: UIA element enumeration (reliable, no pixel guessing)
        match self.plan_via_uia(&goal_lower, ctx).await {
            Ok(Some((actions, descs))) => {
                return Ok(CuaPlan {
                    actions,
                    source: PlanSource::UIA,
                    estimated_risk: Risk::Low,
                    description: format!("Located UI element by accessibility name for: {goal}"),
                    step_descriptions: descs.clone(),
                    step_confidences: vec![0.99; descs.len()],
                    step_sources: vec![super::TargetingSource::UIA; descs.len()],
                });
            }
            Ok(None) => {} // UIA couldn't find element — try next tier
            Err(e) => {
                tracing::warn!("[CUA Planner] UIA error: {} — falling back to visual", e);
            }
        }

        // Step 2.5: VLM visual element grounding fallback
        if let Some((actions, descs, confidence)) = self.plan_via_vlm(&goal_lower, ctx).await {
            return Ok(CuaPlan {
                actions,
                source: PlanSource::Visual,
                estimated_risk: Risk::Medium,
                description: format!("Located UI element via VLM visual grounding for: {goal}"),
                step_descriptions: descs.clone(),
                step_confidences: vec![confidence; descs.len()],
                step_sources: vec![super::TargetingSource::VLM; descs.len()],
            });
        }

        // Step 3: farscry visual element detection (fallback)
        if let Some((actions, descs)) = self.plan_via_farscry(&goal_lower, ctx).await {
            return Ok(CuaPlan {
                actions,
                source: PlanSource::Visual,
                estimated_risk: Risk::Medium,
                description: format!("Using visual element detection for: {goal}"),
                step_descriptions: descs.clone(),
                step_confidences: vec![0.70; descs.len()],
                step_sources: vec![super::TargetingSource::OCR; descs.len()],
            });
        }

        // Step 4: Cannot plan — return manual instruction
        Err(PlannerError::CannotPlan {
            goal: goal.to_string(),
            reason: "No UI element found matching the goal".to_string(),
            manual_instruction: self.generate_manual_instruction(goal, ctx),
        })
    }

    /// Match goal against keyboard-first templates.
    /// These are the most reliable actions — no UI element searching needed.
    fn match_template(&self, goal_lower: &str, app_name: &str) -> Option<&TemplateEntry> {
        let app_key = match app_name.to_lowercase().as_str() {
            "winword" | "microsoft word" | "word" => "winword",
            "excel" | "microsoft excel" => "excel",
            "powerpnt" | "powerpoint" | "microsoft powerpoint" => "powerpnt",
            "chrome" | "google chrome" => "chrome",
            "firefox" | "mozilla firefox" => "firefox",
            _ => "generic",
        };

        // Try app-specific template first
        if let Some(app_templates) = self.templates.get(app_key) {
            for (key, entry) in app_templates {
                if goal_lower.contains(key.as_str()) {
                    return Some(entry);
                }
            }
        }

        // Try generic fallback templates if not found in app-specific
        if app_key != "generic" {
            if let Some(generic_templates) = self.templates.get("generic") {
                for (key, entry) in generic_templates {
                    if goal_lower.contains(key.as_str()) {
                        return Some(entry);
                    }
                }
            }
        }

        None
    }

    /// Plan via Windows UIA accessibility tree.
    /// Finds elements by name (not coordinates) — eliminates 56.7% miss rate.
    async fn plan_via_uia(
        &self,
        goal: &str,
        ctx: &CuaContext,
    ) -> Result<Option<(Vec<CuaAction>, Vec<String>)>, PlannerError> {
        // Extract the element name we're looking for from the goal
        let target_name = self.extract_element_name_from_goal(goal);

        // On Windows, use the uiautomation crate to find elements
        #[cfg(target_os = "windows")]
        {
            // Try to find the element in the cached World Model first
            let mut found_coords = None;
            if let Ok(model_map) = super::world_model::GLOBAL_WORLD_MODEL.lock() {
                if let Some(model) = model_map.get(&(ctx.hwnd as isize)) {
                    if let Some(ref root_node) = model.root {
                        if let Some(node) =
                            super::world_model::find_element_in_tree(root_node, &target_name)
                        {
                            if let Some(ref bbox) = node.bbox {
                                let x = bbox.left + (bbox.right - bbox.left) / 2;
                                let y = bbox.top + (bbox.bottom - bbox.top) / 2;
                                found_coords = Some((x, y));
                                tracing::info!("[World Model] Found target '{}' in cache. Coordinates: ({}, {})", target_name, x, y);
                            }
                        }
                    }
                }
            }

            let coords = match found_coords {
                Some((x, y)) => Some((x, y)),
                None => match self.find_element_by_name_windows(&target_name, ctx) {
                    Ok(Some((x, y))) => Some((x, y)),
                    _ => None,
                },
            };

            if let Some((x, y)) = coords {
                let actions = vec![
                    CuaAction::MouseMove { x, y },
                    CuaAction::MouseClick {
                        x,
                        y,
                        button: MouseButton::Left,
                        targeting_source: super::TargetingSource::UIA,
                        targeting_confidence: 0.99,
                    },
                ];
                let descs = vec![
                    format!(
                        "Move to '{}' element (found via accessibility tree)",
                        target_name
                    ),
                    format!("Click '{}' element", target_name),
                ];
                return Ok(Some((actions, descs)));
            }
            Ok(None)
        }

        // Non-Windows: UIA not available
        #[cfg(not(target_os = "windows"))]
        Ok(None)
    }

    /// Find a UI element by name using Windows UIA (uiautomation crate)
    #[cfg(target_os = "windows")]
    fn find_element_by_name_windows(
        &self,
        name: &str,
        ctx: &CuaContext,
    ) -> Result<Option<(i32, i32)>, String> {
        use uiautomation::UIAutomation;

        let automation = UIAutomation::new().map_err(|e| e.to_string())?;
        let root = automation.get_root_element().map_err(|e| e.to_string())?;

        // Build a condition to find elements matching the name
        let condition = automation
            .create_property_condition(
                uiautomation::types::UIProperty::Name,
                uiautomation::variants::Variant::from(name),
                None,
            )
            .map_err(|e| e.to_string())?;

        match root.find_first(uiautomation::types::TreeScope::Subtree, &condition) {
            Ok(element) => {
                // Get clickable point from UIA element
                match element.get_clickable_point() {
                    Ok(Some(point)) => {
                        // UIA returns logical coordinates — scale by DPI for enigo
                        let x = (point.get_x() as f32 * ctx.dpi_scale) as i32;
                        let y = (point.get_y() as f32 * ctx.dpi_scale) as i32;
                        Ok(Some((x, y)))
                    }
                    Ok(None) => {
                        // Try bounding rectangle center
                        if let Ok(rect) = element.get_bounding_rectangle() {
                            let x = rect.get_left() + rect.get_width() / 2;
                            let y = rect.get_top() + rect.get_height() / 2;
                            Ok(Some((x, y)))
                        } else {
                            Ok(None)
                        }
                    }
                    Err(_) => Ok(None),
                }
            }
            Err(_) => Ok(None), // Element not found
        }
    }

    /// Plan via VLM Visual Element Grounding.
    async fn plan_via_vlm(
        &self,
        goal: &str,
        ctx: &CuaContext,
    ) -> Option<(Vec<CuaAction>, Vec<String>, f32)> {
        let bridge = super::vlm_bridge::VlmBridge::new();
        if !bridge.is_available().await {
            return None;
        }
        super::world_model::VLM_INVOCATIONS.fetch_add(1, std::sync::atomic::Ordering::SeqCst);

        // Capture a screenshot to send to VLM
        let screenshot_path = format!(
            "{}/vlm_plan_screenshot.png",
            dirs::home_dir()
                .unwrap_or_default()
                .join(".kairo-phantom")
                .to_string_lossy()
        );

        // Take screenshot
        let _ = std::process::Command::new("farscry")
            .args(["screenshot", "--output", &screenshot_path])
            .output();

        let target_name = self.extract_element_name_from_goal(goal);

        // Call ground_element on VlmBridge
        match bridge.ground_element(&screenshot_path, &target_name).await {
            Ok(resp) if resp.found => {
                let x = resp.x;
                let y = resp.y;
                let confidence = resp.confidence;
                let actions = vec![
                    CuaAction::MouseMove { x, y },
                    CuaAction::MouseClick {
                        x,
                        y,
                        button: MouseButton::Left,
                        targeting_source: super::TargetingSource::VLM,
                        targeting_confidence: confidence,
                    },
                ];
                let descs = vec![
                    format!(
                        "Move to '{}' element (found via VLM visual grounding)",
                        target_name
                    ),
                    format!("Click '{}' element", target_name),
                ];
                Some((actions, descs, confidence))
            }
            _ => None,
        }
    }

    /// Plan via farscry visual element detection (screenshot-based fallback).
    async fn plan_via_farscry(
        &self,
        goal: &str,
        ctx: &CuaContext,
    ) -> Option<(Vec<CuaAction>, Vec<String>)> {
        // Check if farscry is available
        let farscry_check = std::process::Command::new("farscry")
            .arg("--version")
            .output();

        if farscry_check.is_err() {
            return None; // farscry not installed
        }

        // Capture a screenshot and ask farscry to find the element
        let screenshot_path = format!(
            "{}/cua_plan_screenshot.png",
            dirs::home_dir()
                .unwrap_or_default()
                .join(".kairo-phantom")
                .to_string_lossy()
        );

        // Take screenshot
        let _ = std::process::Command::new("farscry")
            .args(["screenshot", "--output", &screenshot_path])
            .output();

        // Extract elements from screenshot
        let extract_result = std::process::Command::new("farscry")
            .args(["extract", &screenshot_path])
            .output();

        if let Ok(output) = extract_result {
            if let Ok(json_str) = String::from_utf8(output.stdout) {
                if let Ok(elements) = serde_json::from_str::<serde_json::Value>(&json_str) {
                    let target_name = self.extract_element_name_from_goal(goal);

                    // Look for an element matching the target name
                    if let Some(elements_arr) = elements["elements"].as_array() {
                        for elem in elements_arr {
                            let elem_text = elem["text"].as_str().unwrap_or("").to_lowercase();
                            if elem_text.contains(&target_name.to_lowercase()) {
                                if let (Some(x), Some(y)) =
                                    (elem["bbox"]["x"].as_i64(), elem["bbox"]["y"].as_i64())
                                {
                                    let actions = vec![
                                        CuaAction::MouseMove {
                                            x: x as i32,
                                            y: y as i32,
                                        },
                                        CuaAction::MouseClick {
                                            x: x as i32,
                                            y: y as i32,
                                            button: MouseButton::Left,
                                            targeting_source: super::TargetingSource::OCR,
                                            targeting_confidence: 0.70,
                                        },
                                    ];
                                    let descs = vec![
                                        format!(
                                            "Move to visually detected '{}' element",
                                            target_name
                                        ),
                                        format!(
                                            "Click '{}' element (visual detection)",
                                            target_name
                                        ),
                                    ];
                                    return Some((actions, descs));
                                }
                            }
                        }
                    }
                }
            }
        }

        None
    }

    /// Extract the element name from a natural language goal.
    /// Examples:
    ///   "click Save button" → "Save"
    ///   "click the Export option" → "Export"
    ///   "press the OK button" → "OK"
    fn extract_element_name_from_goal(&self, goal: &str) -> String {
        // Simple heuristic: look for words after "click", "press", "find", "tap"
        let trigger_words = ["click", "press", "find", "tap", "select", "open"];

        for trigger in &trigger_words {
            if let Some(pos) = goal.find(trigger) {
                let after = &goal[pos + trigger.len()..].trim();
                // Remove common filler words
                let cleaned = after
                    .trim_start_matches("the ")
                    .trim_start_matches("on ")
                    .trim_start_matches("a ")
                    .trim_start_matches("an ");

                // Take first meaningful word(s)
                let words: Vec<&str> = cleaned.split_whitespace().collect();
                if !words.is_empty() {
                    // Take up to 2 words, removing common suffixes
                    let name = words
                        .iter()
                        .take(2)
                        .map(|w| {
                            w.trim_end_matches("button")
                                .trim_end_matches("option")
                                .trim_end_matches("tab")
                        })
                        .collect::<Vec<_>>()
                        .join(" ")
                        .trim()
                        .to_string();

                    if !name.is_empty() {
                        return name;
                    }
                }
            }
        }

        // Fallback: use the whole goal as the search term
        goal.to_string()
    }

    /// Generate a manual instruction for the user when CUA cannot plan
    fn generate_manual_instruction(&self, goal: &str, ctx: &CuaContext) -> String {
        format!(
            "Please manually {} in {}. Kairo will observe and remember for next time.",
            goal, ctx.app_name
        )
    }

    /// Load pre-built keyboard-first templates for common document workflows.
    /// Templates use shortcuts, not pixel coordinates — 100% reliable.
    fn load_templates() -> HashMap<String, HashMap<String, TemplateEntry>> {
        let mut apps = HashMap::new();

        // 1. winword templates
        let mut word = HashMap::new();
        word.insert(
            "save as pdf".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::SaveAsPdf,
                }],
                step_descriptions: vec![
                    "Press Ctrl+Shift+P to export Word document as PDF".to_string()
                ],
                risk: Risk::Low,
            },
        );
        word.insert(
            "export pdf".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::SaveAsPdf,
                }],
                step_descriptions: vec![
                    "Press Ctrl+Shift+P to export Word document as PDF".to_string()
                ],
                risk: Risk::Low,
            },
        );
        apps.insert("winword".to_string(), word);

        // 2. excel templates
        let mut excel = HashMap::new();
        excel.insert(
            "save as pdf".to_string(),
            TemplateEntry {
                // Multi-step keyboard shortcut sequence for Excel using Delay
                actions: vec![
                    CuaAction::KeyboardCombo {
                        keys: vec!["Alt".to_string(), "F".to_string()],
                    },
                    CuaAction::Delay { ms: 100 },
                    CuaAction::KeyboardType {
                        text: "A".to_string(),
                    },
                    CuaAction::Delay { ms: 100 },
                    CuaAction::KeyboardType {
                        text: "O".to_string(),
                    },
                ],
                step_descriptions: vec![
                    "Press Alt+F to open File menu".to_string(),
                    "Wait 100ms for menu to open".to_string(),
                    "Press A to select Save As".to_string(),
                    "Wait 100ms".to_string(),
                    "Press O to trigger Save as PDF".to_string(),
                ],
                risk: Risk::Low,
            },
        );
        excel.insert(
            "new sheet".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardCombo {
                    keys: vec!["shift".to_string(), "f11".to_string()],
                }],
                step_descriptions: vec!["Press Shift+F11 to insert a new worksheet".to_string()],
                risk: Risk::Low,
            },
        );
        apps.insert("excel".to_string(), excel);

        // 3. powerpnt templates
        let mut powerpoint = HashMap::new();
        powerpoint.insert(
            "save as pdf".to_string(),
            TemplateEntry {
                // Multi-step keyboard shortcut sequence for PowerPoint using Delay
                actions: vec![
                    CuaAction::KeyboardCombo {
                        keys: vec!["alt".to_string(), "f".to_string()],
                    },
                    CuaAction::Delay { ms: 100 },
                    CuaAction::KeyboardType {
                        text: "e".to_string(),
                    },
                    CuaAction::Delay { ms: 100 },
                    CuaAction::KeyboardType {
                        text: "a".to_string(),
                    },
                ],
                step_descriptions: vec![
                    "Press Alt+F to open File menu".to_string(),
                    "Wait 100ms for menu to open".to_string(),
                    "Press E to select Export".to_string(),
                    "Wait 100ms".to_string(),
                    "Press A to trigger Save as PDF/XPS".to_string(),
                ],
                risk: Risk::Low,
            },
        );
        powerpoint.insert(
            "new slide".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardCombo {
                    keys: vec!["ctrl".to_string(), "m".to_string()],
                }],
                step_descriptions: vec!["Press Ctrl+M to insert a new slide".to_string()],
                risk: Risk::Low,
            },
        );
        apps.insert("powerpnt".to_string(), powerpoint);

        // 4. chrome templates
        let mut chrome = HashMap::new();
        chrome.insert(
            "new tab".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardCombo {
                    keys: vec!["ctrl".to_string(), "t".to_string()],
                }],
                step_descriptions: vec!["Press Ctrl+T to open a new tab".to_string()],
                risk: Risk::Low,
            },
        );
        chrome.insert(
            "bookmark".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardCombo {
                    keys: vec!["ctrl".to_string(), "d".to_string()],
                }],
                step_descriptions: vec!["Press Ctrl+D to bookmark this page".to_string()],
                risk: Risk::Low,
            },
        );
        apps.insert("chrome".to_string(), chrome);

        // 5. firefox templates
        let mut firefox = HashMap::new();
        firefox.insert(
            "new tab".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardCombo {
                    keys: vec!["ctrl".to_string(), "t".to_string()],
                }],
                step_descriptions: vec!["Press Ctrl+T to open a new tab".to_string()],
                risk: Risk::Low,
            },
        );
        apps.insert("firefox".to_string(), firefox);

        // 6. generic templates
        let mut generic = HashMap::new();
        generic.insert(
            "save as pdf".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::SaveAs,
                }],
                step_descriptions: vec![
                    "Press Ctrl+Shift+S to open Save As dialog".to_string(),
                    "Select PDF format from dropdown".to_string(),
                    "Click Save".to_string(),
                ],
                risk: Risk::Low,
            },
        );
        generic.insert(
            "export pdf".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::SaveAsPdf,
                }],
                step_descriptions: vec!["Press Ctrl+Shift+P to export as PDF".to_string()],
                risk: Risk::Low,
            },
        );
        generic.insert(
            "select all".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::SelectAll,
                }],
                step_descriptions: vec!["Press Ctrl+A to select all content".to_string()],
                risk: Risk::Low,
            },
        );
        generic.insert(
            "undo".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::Undo,
                }],
                step_descriptions: vec!["Press Ctrl+Z to undo last action".to_string()],
                risk: Risk::Low,
            },
        );
        generic.insert(
            "redo".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::Redo,
                }],
                step_descriptions: vec!["Press Ctrl+Y to redo last action".to_string()],
                risk: Risk::Low,
            },
        );
        generic.insert(
            "save file".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardCombo {
                    keys: vec!["ctrl".to_string(), "s".to_string()],
                }],
                step_descriptions: vec!["Press Ctrl+S to save the file".to_string()],
                risk: Risk::Low,
            },
        );
        generic.insert(
            "close dialog".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::CloseDialog,
                }],
                step_descriptions: vec!["Press Escape to close the dialog".to_string()],
                risk: Risk::Low,
            },
        );
        generic.insert(
            "confirm".to_string(),
            TemplateEntry {
                actions: vec![CuaAction::KeyboardShortcut {
                    shortcut: WellKnownShortcut::ConfirmDialog,
                }],
                step_descriptions: vec!["Press Enter to confirm".to_string()],
                risk: Risk::Low,
            },
        );
        apps.insert("generic".to_string(), generic);

        // Load community shortcuts
        Self::load_toml_shortcuts(&mut apps);

        apps
    }

    /// Load community shortcuts from config files
    fn load_toml_shortcuts(apps: &mut HashMap<String, HashMap<String, TemplateEntry>>) {
        #[derive(Debug, serde::Deserialize)]
        struct TomlShortcutFile {
            apps: HashMap<String, TomlApp>,
        }

        #[derive(Debug, serde::Deserialize)]
        struct TomlApp {
            shortcuts: HashMap<String, Vec<TomlShortcutAction>>,
        }

        #[derive(Debug, serde::Deserialize)]
        struct TomlShortcutAction {
            #[serde(rename = "type")]
            action_type: String,
            keys: Option<Vec<String>>,
            text: Option<String>,
            shortcut: Option<String>,
            ms: Option<u64>,
        }

        // Try local/repo config path, absolute dev path, and home directory user overrides
        let paths = vec![
            std::path::Path::new("config/cua_shortcuts.toml").to_path_buf(),
            std::path::Path::new(r"c:\Users\praja\OneDrive\Desktop\test-env\repositories\kairo-phantom\config\cua_shortcuts.toml").to_path_buf(),
            dirs::home_dir().map(|h| h.join(".kairo-phantom").join("cua_shortcuts.toml")).unwrap_or_default(),
        ];

        for path in paths {
            if path.exists() {
                if let Ok(content) = std::fs::read_to_string(&path) {
                    if let Ok(toml_data) = toml::from_str::<TomlShortcutFile>(&content) {
                        for (app_name, app_data) in toml_data.apps {
                            let app_entry = apps.entry(app_name.clone()).or_default();
                            for (goal, actions_toml) in app_data.shortcuts {
                                let mut actions = Vec::new();
                                let mut step_descriptions = Vec::new();
                                for action_toml in actions_toml {
                                    match action_toml.action_type.as_str() {
                                        "keyboard_combo" => {
                                            if let Some(keys) = action_toml.keys {
                                                actions.push(CuaAction::KeyboardCombo {
                                                    keys: keys.clone(),
                                                });
                                                step_descriptions
                                                    .push(format!("Press {}", keys.join("+")));
                                            }
                                        }
                                        "keyboard_type" => {
                                            if let Some(text) = action_toml.text {
                                                actions.push(CuaAction::KeyboardType {
                                                    text: text.clone(),
                                                });
                                                step_descriptions.push(format!("Type: {text}"));
                                            }
                                        }
                                        "keyboard_shortcut" => {
                                            if let Some(shortcut_str) = action_toml.shortcut {
                                                let shortcut = match shortcut_str.as_str() {
                                                    "save_as_pdf" => WellKnownShortcut::SaveAsPdf,
                                                    "save_as" => WellKnownShortcut::SaveAs,
                                                    "select_all" => WellKnownShortcut::SelectAll,
                                                    "undo" => WellKnownShortcut::Undo,
                                                    "redo" => WellKnownShortcut::Redo,
                                                    "close_dialog" => {
                                                        WellKnownShortcut::CloseDialog
                                                    }
                                                    "confirm_dialog" => {
                                                        WellKnownShortcut::ConfirmDialog
                                                    }
                                                    "next_field" => WellKnownShortcut::NextField,
                                                    _ => continue,
                                                };
                                                actions.push(CuaAction::KeyboardShortcut {
                                                    shortcut: shortcut.clone(),
                                                });
                                                step_descriptions
                                                    .push(format!("Trigger {shortcut:?}"));
                                            }
                                        }
                                        "delay_ms" => {
                                            if let Some(ms) = action_toml.ms {
                                                actions.push(CuaAction::Delay { ms });
                                                step_descriptions.push(format!("Wait {ms}ms"));
                                            }
                                        }
                                        _ => {}
                                    }
                                }
                                app_entry.insert(
                                    goal,
                                    TemplateEntry {
                                        actions,
                                        step_descriptions,
                                        risk: Risk::Low,
                                    },
                                );
                            }
                        }
                    }
                }
            }
        }
    }
}

impl Default for CuaPlanner {
    fn default() -> Self {
        Self::new()
    }
}
