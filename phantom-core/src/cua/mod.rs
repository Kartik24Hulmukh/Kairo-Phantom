//! # CUA — Computer Use Agent Module
//!
//! UIA-first, document-aware, governance-gated GUI automation.
//!
//! ## Architecture
//! - **Tier 0**: File API (python-docx, openpyxl) — 95% of tasks
//! - **Tier 1**: UIA SetValue — browser fields
//! - **Tier 2**: MCP server — Figma/Excel COM
//! - **Tier 3 (this module)**: CUA — only when Tiers 0-2 all fail
//!
//! ## Safety Design
//! - Hard Rust gate (no LLM makes safety decisions)
//! - UIA-first targeting (eliminates 56.7% coordinate miss rate)
//! - Rate limiter: 10 actions/60 seconds
//! - Blocklist: Task Manager, Registry Editor, password managers
//! - User approval required before ANY action (Tab in GRP)
//! - Esc cancels everything within 100ms
//!
//! All code gated behind `#[cfg(feature = "cua")]`.

#[cfg(feature = "cua")]
pub mod config;
#[cfg(feature = "cua")]
pub mod cua_executor;
#[cfg(feature = "cua")]
pub mod cua_gate;
#[cfg(feature = "cua")]
pub mod cua_planner;
#[cfg(feature = "cua")]
pub mod vlm_bridge;
#[cfg(feature = "cua")]
pub mod world_model;
// GRP CUA plan display (always available -- needed by GRP overlay regardless of feature)
pub mod grp_cua_plan;

use serde::{Deserialize, Serialize};

/// Source of coordinate targeting for an action
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[allow(clippy::upper_case_acronyms)]
pub enum TargetingSource {
    Keyboard,   // 100% reliable — keyboard shortcut, no visual targeting
    UIA,        // ~99% for accessible apps — found by accessibility name
    VLM,        // 88-97% for any app — Qwen2.5-VL visual grounding
    OCR,        // ~70% — farscry text detection
    Coordinate, // <43% — raw pixel coordinate (should almost never be used)
}

/// All possible CUA actions.
/// Dispatched by CuaExecutor via enigo (primary) or cua-driver (fallback).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum CuaAction {
    /// Click mouse button at absolute screen coordinates (DPI-scaled internally)
    MouseClick {
        x: i32,
        y: i32,
        button: MouseButton,
        targeting_source: TargetingSource,
        targeting_confidence: f32,
    },
    /// Double-click at absolute screen coordinates
    MouseDoubleClick { x: i32, y: i32, button: MouseButton },
    /// Move mouse to absolute screen coordinates without clicking
    MouseMove { x: i32, y: i32 },
    /// Scroll mouse wheel
    MouseScroll {
        direction: ScrollDirection,
        amount: i32,
    },
    /// Type a string of text (Unicode-safe)
    KeyboardType { text: String },
    /// Press a key combination (e.g., ["ctrl", "shift", "s"])
    KeyboardCombo { keys: Vec<String> },
    /// Execute a well-known keyboard shortcut (more reliable than mouse navigation)
    KeyboardShortcut { shortcut: WellKnownShortcut },
    /// Capture a screenshot (used for before/after verification)
    Screenshot,
    /// Delay for a number of milliseconds (useful for keyboard settles)
    Delay { ms: u64 },
}

/// Well-known keyboard shortcuts — more reliable than pixel-clicking through menus.
/// These are hard-coded per-app where needed.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum WellKnownShortcut {
    /// Save As PDF (Ctrl+Shift+P in Word, or File→Export→PDF)
    SaveAsPdf,
    /// Save As dialog (Ctrl+Shift+S)
    SaveAs,
    /// Select All (Ctrl+A)
    SelectAll,
    /// Undo (Ctrl+Z)
    Undo,
    /// Redo (Ctrl+Y)
    Redo,
    /// Close dialog / cancel (Escape)
    CloseDialog,
    /// Confirm dialog (Enter)
    ConfirmDialog,
    /// Next field (Tab)
    NextField,
}

/// Mouse button enum
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum MouseButton {
    Left,
    Right,
    Middle,
}

/// Scroll direction
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ScrollDirection {
    Up,
    Down,
    Left,
    Right,
}

/// Context about the target window for a CUA operation.
/// Populated before calling CuaGate.validate_action().
///
/// `Serialize`/`Deserialize` required for audit-log JSON serialization.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CuaContext {
    /// Win32 window handle (HWND as isize for cross-boundary safety)
    pub hwnd: isize,
    /// Window title text (used for blocklist matching)
    pub window_title: String,
    /// Window bounding rect in screen coordinates
    pub window_rect: WindowRect,
    /// DPI scaling factor (1.0 = 100%, 1.25 = 125%, 1.5 = 150%, 2.0 = 200%)
    /// CRITICAL: All mouse coordinates MUST be multiplied by this before use
    pub dpi_scale: f32,
    /// Application name (Word, Chrome, Canva, etc.)
    pub app_name: String,
    /// Path to before-screenshot captured by CuaGate (populated after validate_action)
    pub before_screenshot_path: Option<String>,
}

impl Default for CuaContext {
    fn default() -> Self {
        Self {
            hwnd: 0,
            window_title: String::new(),
            window_rect: WindowRect::default(),
            dpi_scale: 1.0,
            app_name: String::new(),
            before_screenshot_path: None,
        }
    }
}

/// Bounding rectangle in screen coordinates
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct WindowRect {
    pub left: i32,
    pub top: i32,
    pub right: i32,
    pub bottom: i32,
}

/// Result of a CUA execution attempt
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub enum CuaResult {
    /// Action executed and verified successfully
    Success(CuaVerification),
    /// Action was cancelled (ESC pressed)
    Cancelled,
    /// Action failed after all retries
    Failed(String),
}

/// Evidence from farscry post-execution verification
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CuaVerification {
    /// Whether farscry confirmed the expected change occurred
    pub success: bool,
    /// Path to after-screenshot for audit log
    pub after_screenshot_path: String,
    /// SHA-256 hash of before screenshot
    pub before_hash: String,
    /// SHA-256 hash of after screenshot
    pub after_hash: String,
}

/// Plan source — how the action sequence was generated
#[allow(clippy::upper_case_acronyms)]
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub enum PlanSource {
    /// Keyboard shortcut template (most reliable)
    Template,
    /// UIA accessibility tree element targeting
    UIA,
    /// farscry visual element detection (fallback)
    Visual,
}

/// Risk level assigned by planner
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub enum Risk {
    Low,
    Medium,
    High,
}

/// A planned CUA action sequence ready for user approval
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CuaPlan {
    /// Ordered list of actions to execute
    pub actions: Vec<CuaAction>,
    /// How this plan was generated
    pub source: PlanSource,
    /// Estimated risk level
    pub estimated_risk: Risk,
    /// Human-readable description for GRP display
    pub description: String,
    /// Numbered step descriptions for GRP mini-plan display
    pub step_descriptions: Vec<String>,
    /// Confidence score per step (0.0 to 1.0)
    pub step_confidences: Vec<f32>,
    /// Targeting source for each step
    pub step_sources: Vec<TargetingSource>,
}

/// Which execution backend to use
#[derive(Debug, Clone, PartialEq)]
pub enum CuaBackend {
    /// enigo crate — primary, cross-platform keyboard/mouse
    Enigo,
    /// cua-driver binary — fallback, no admin required
    CuaDriver,
}

impl CuaBackend {
    /// Get fallback backend (Enigo falls back to CuaDriver and vice versa)
    pub fn fallback(&self) -> Option<CuaBackend> {
        match self {
            CuaBackend::Enigo => Some(CuaBackend::CuaDriver),
            CuaBackend::CuaDriver => None,
        }
    }
}

/// Rollback actions to undo state changes
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub enum RollbackEntry {
    /// Undo keystroke by sending Ctrl+Z
    UndoKeystroke,
    /// Restore a file to its original content
    RestoreFile {
        path: std::path::PathBuf,
        content: Vec<u8>,
    },
}
