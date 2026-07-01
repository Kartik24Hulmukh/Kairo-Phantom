// phantom-core/src/lib.rs
//
// Lint configuration:
// Several modules contain scaffolded APIs that are intentionally defined but
// not yet called in main.rs (e.g., telemetry, eval suite, WASM sandbox,
// governance, UIA adapters). These will be activated in future milestones.
// We suppress dead_code and unused warnings crate-wide to avoid obscuring
// real issues with scaffolding noise. This is standard practice for library
// crates with forward-declared APIs.
#![allow(dead_code)]
#![allow(unused_imports)]
#![allow(unused_variables)]
#![allow(clippy::empty_line_after_doc_comments)]

pub mod ai;
pub mod api;
pub mod config;
pub mod context;
pub mod crdt;
pub mod hotkey;
pub mod injector;
pub mod integration;
pub mod swarm;
pub mod uia;

pub mod background_worker;
pub mod collaborative;
pub mod command_protocol;
pub mod context7;
pub mod context_optimizer;
pub mod document_context;
pub mod embedding; // Phase 0.4: sqlite-vec + fastembed semantic search
pub mod extractors;
pub mod ghost_session;
pub mod governance;
pub mod guardrails;
pub mod identity;
pub mod image_pipeline;
pub mod intent_gate;
pub mod kami_export;
pub mod mcp_bridge;
pub mod mcp_client;
pub mod memory;
pub mod memory_store;
pub mod memory_vault;
pub mod pdf_context; // Domain 4: PDF SmartContextCapture structs
pub mod perf_engine;
pub mod persona;
pub mod pii_guard;
pub mod pipeline;
pub mod planning_engine;
pub mod platform;
pub mod plugin;
pub mod pro;
/// Phase 1 Hardening: strict // protocol gate — returns None for non-command text.
pub mod prompt_parser;
pub mod quality_gate;
pub mod response_validator;
pub mod retry_policy;
pub mod sentinel;
pub mod skill_factory;
pub mod skills;
pub mod tolaria_bridge;
pub mod verify;
pub mod writing_pipeline;
pub mod yjs_peer;

/// Message bus between all threads
#[derive(Debug, Clone)]
pub enum PhantomEvent {
    /// User triggered the hotkey — materialize AI suggestion
    HotkeyPressed,
    /// UIA reader captured the current focused element text
    ContextCaptured(String),
    /// AI returned a suggestion
    SuggestionReady(String),
    /// User started typing — abort current AI stream
    UserTyping,
    /// Domain 8: Alt+V — voice dictation trigger
    VoicePressed,
    /// Domain 8: Alt+Shift+M — screen context capture trigger
    ScreenContextPressed,
    /// User pressed Ctrl+Shift+Z — undo last injection
    UndoPressed,
    /// Skill save approved by the user (pressing Tab)
    SkillSaveApproved,
    /// Skill save cancelled by the user (other keys/typing)
    SkillSaveCancelled,
    /// CUA execution approved by the user (pressing Tab)
    CuaApproved,
    /// CUA execution cancelled by the user (other keys/Escape)
    CuaCancelled,
    /// Shutdown signal
    Shutdown,
}
pub mod mcp_auth;

pub mod waza_sdk;

// ── 100x Roadmap Modules ──────────────────────────────────────────────────────
pub mod cross_doc_consistency;
pub mod deep_presenter;
pub mod excel_formula;
pub mod health_check;
pub mod kpx_export; // P1-A4: .kpx portable memory export/import
pub mod lan_sync;
pub mod memory_seeder; // P1-A2: Seed MemMachine from existing doc folder
pub mod ollama_bootstrap; // P0-A2: Ollama auto-detection & background setup
pub mod section_summarizer;
pub mod startup_timer; // P0-A1: Startup checkpoint profiler
pub mod toast_notification; // P0-B2: PAHF toast overlay (replaces doc injection)
pub mod waza_registry;

// ── Phase 1: Python Sidecar + Document-Native Pipeline ────────────────────────
pub mod doc_prompt_builder;
pub mod sidecar_client; // TCP client → Python sidecar (DOCX/XLSX/PPTX/PDF I/O) // Format-specific LLM prompt builder + JSON op parser

// ── Phase 4A: Markdown Section-Aware Writer ───────────────────────────────────
pub mod code_context;
pub mod code_injector;
pub mod md_writer; // pulldown-cmark AST-aware markdown insertion

// ── Domain 8: Multimodal Input ──────────────────────────────────────────────
pub mod screen_context;
pub mod tts_engine;
pub mod voice_engine;
pub mod wake_word;

// ── Domain 9: Enterprise Governance & Compliance ────────────────────────────
pub mod prompt_injection_firewall; // 50-detector 6-layer prompt injection firewall

// ── FarScry: Foreground App Watcher ─────────────────────────────────────────
pub mod app_watcher; // Win32 foreground window polling → AppChangedEvent

// ── CUA: Computer Use Agent ──────────────────────────────────────────────────
// UIA-first GUI automation (Tier 3 — only when File API + UIA SetValue + MCP all fail)
// Core types (CuaAction, CuaContext, etc.) are always available.
// Implementation modules (cua_gate, cua_executor, cua_planner, config) are gated
// behind #[cfg(feature = "cua")] — default builds have zero CUA code.
pub mod cua;

pub mod monitor;
