/// HTTP API server for phantom-core.
/// The Tauri overlay calls these endpoints via localhost:7437.
use axum::{
    extract::State,
    http::StatusCode,
    response::Json,
    routing::{get, post},
    Router,
};
use tokio::net::TcpListener;
use tracing::info;

use crate::ai::AiBackend;
use crate::command_protocol::CommandMode;
use crate::context::ContextEngine;
use crate::crdt::CrdtSession;
use crate::document_context::{DocumentContext, ExtractorRegistry};
use crate::injector::HumanizedInjector as Injector;
use crate::platform::AccessibilityReader;
use crate::swarm::{AgentType, SwarmOrchestrator};
use crate::uia::UiaReader;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

pub const PORT: u16 = 7437;

#[derive(Clone)]
pub struct ApiState {
    pub crdt: Arc<CrdtSession>,
    pub uia: Arc<UiaReader>,
    pub injector: Arc<Injector>,
    pub ai: Arc<dyn AiBackend>,
    pub context_engine: Arc<ContextEngine>,
    pub extractor_registry: Arc<ExtractorRegistry>,
    pub swarm_engine: Arc<SwarmOrchestrator>,
    pub mcp_agent_override: Arc<std::sync::Mutex<Option<String>>>,
}

#[derive(Deserialize)]
pub struct MaterializeRequest {
    pub context: Option<String>,
}

#[derive(Serialize)]
pub struct MaterializeResponse {
    pub suggestion: String,
    pub word_count: usize,
    pub char_count: usize,
}

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: &'static str,
    pub version: &'static str,
}

#[derive(Serialize)]
/*
pub struct ContextResponse {
    pub process_name: String,
    pub window_title: String,
    pub extracted_text: String,
}
*/
#[derive(Deserialize)]
pub struct InjectRequest {
    pub text: String,
}

#[derive(Deserialize)]
pub struct AskRequest {
    pub prompt: String,
}

#[derive(Deserialize)]
pub struct CompleteRequest {
    pub prompt: String,
    #[serde(default)]
    pub context: String,
}

#[derive(Serialize)]
pub struct AskResponse {
    pub response: String,
}

#[derive(Serialize)]
pub struct AppResponse {
    pub process: String,
    pub environment: String,
}

#[derive(Deserialize)]
pub struct AgentRequest {
    pub agent: String,
}

#[derive(Deserialize)]
pub struct ImageGenerateRequest {
    pub prompt: String,
    #[serde(default)]
    pub backend: String,
}

#[derive(Serialize)]
pub struct ImageGenerateResponse {
    pub status: String,
    pub base64_data: String,
    pub mime_type: String,
    pub backend_used: String,
}

#[derive(Deserialize)]
pub struct MobileSyncRequest {
    pub device_id: String,
    pub content: String,
    pub tags: Vec<String>,
}

#[derive(Serialize)]
pub struct MobileSyncResponse {
    pub status: String,
    pub sync_id: String,
}

/// GET /health
async fn health() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        version: env!("CARGO_PKG_VERSION"),
    })
}

/// GET /context — MCP Tool: read context
async fn get_context(State(state): State<ApiState>) -> Json<DocumentContext> {
    let raw_text = state
        .uia
        .get_focused_text()
        .or_else(|_| state.uia.get_clipboard_text())
        .unwrap_or_default();

    let app_ctx = state.context_engine.capture(&raw_text);

    let doc_ctx = if let Some(ref file_path) = app_ctx.file_path {
        state
            .extractor_registry
            .extract(file_path, &app_ctx.prompt_text, app_ctx.active_slide)
            .unwrap_or_else(|| {
                DocumentContext::from_raw_text(
                    &app_ctx.prompt_text,
                    &app_ctx.document_text,
                    app_ctx.environment.to_doc_kind(),
                )
            })
    } else {
        DocumentContext::from_raw_text(
            &app_ctx.prompt_text,
            &app_ctx.document_text,
            app_ctx.environment.to_doc_kind(),
        )
    };

    Json(doc_ctx)
}

/// POST /inject — MCP Tool: ghost write
async fn inject(
    State(state): State<ApiState>,
    Json(req): Json<InjectRequest>,
) -> Result<Json<()>, (StatusCode, String)> {
    let injector = state.injector.clone();
    tokio::task::spawn_blocking(move || injector.type_text(&req.text));
    Ok(Json(()))
}

/// POST /ask — MCP Tool: ask (context-aware swarm generation + inject)
async fn ask(
    State(state): State<ApiState>,
    Json(req): Json<AskRequest>,
) -> Result<Json<AskResponse>, (StatusCode, String)> {
    let raw_text = state
        .uia
        .get_focused_text()
        .or_else(|_| state.uia.get_clipboard_text())
        .unwrap_or_default();

    let app_ctx = state.context_engine.capture(&raw_text);

    let doc_ctx = if let Some(ref file_path) = app_ctx.file_path {
        state
            .extractor_registry
            .extract(file_path, &app_ctx.prompt_text, app_ctx.active_slide)
            .unwrap_or_else(|| {
                DocumentContext::from_raw_text(
                    &app_ctx.prompt_text,
                    &app_ctx.document_text,
                    app_ctx.environment.to_doc_kind(),
                )
            })
    } else {
        DocumentContext::from_raw_text(
            &app_ctx.prompt_text,
            &app_ctx.document_text,
            app_ctx.environment.to_doc_kind(),
        )
    };

    // Check if MCP override is set
    let override_agent = {
        let mut lock = state.mcp_agent_override.lock().unwrap();
        lock.take() // Use it once and clear it
    };

    let (mode, prompt) = CommandMode::from_prompt(&doc_ctx.prompt_text);

    let (target_backend, profile) = if let Some(agent_name) = override_agent {
        let agent_type = match agent_name.to_lowercase().as_str() {
            "design" => AgentType::DesignAndMedia,
            "reasoning" => AgentType::ReasoningAndLogic,
            "student" => AgentType::StudentTutor,
            "engineer" => AgentType::Engineer,
            "data" => AgentType::DataAnalyst,
            _ => AgentType::ContentAndAllRounder,
        };
        state
            .swarm_engine
            .get_backend_and_profile_by_type(&agent_type, &doc_ctx)
    } else {
        state.swarm_engine.route(&doc_ctx, &mode).await
    };

    // ── Determine final prompt: API request takes priority over UIA capture ──
    // req.prompt is the actual user intent from the API caller.
    // doc_ctx.prompt_text is UIA-captured screen text (used only as fallback context).
    let final_prompt = if !req.prompt.is_empty() {
        req.prompt.as_str()
    } else if !prompt.is_empty() {
        prompt.as_str()
    } else {
        return Err((StatusCode::BAD_REQUEST, "No prompt provided".into()));
    };

    // Use a clear, helpful system directive for API callers
    // (not the internal swarm directive which is designed for ghost-session GUI injection)
    let api_system = format!(
        "{} You are a helpful AI assistant. Answer the user's request directly and completely. \
         Do not ask for clarification unless the request is genuinely ambiguous. \
         Output only the requested content — no meta-commentary, no preamble.",
        profile.system_directive
    );

    let resp = target_backend
        .complete(&api_system, final_prompt)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    // Strip [REPLACE] prefix if present (artifact from WritingPipeline)
    let clean_resp = resp
        .strip_prefix("[REPLACE]")
        .unwrap_or(&resp)
        .trim()
        .to_string();

    let injector = state.injector.clone();
    let text = clean_resp.clone();
    #[allow(clippy::let_underscore_future)]
    let _ = tokio::task::spawn_blocking(move || injector.type_text(&text));

    Ok(Json(AskResponse {
        response: clean_resp,
    }))
}

/// POST /api/complete — CI orchestrator endpoint
/// Called by kairo_test_utils.call_kairo() in stub mode.
/// Uses the same AI backend pipeline as /ask but accepts {prompt, context}
/// and returns {text: ...} without injecting keystrokes.
async fn complete(
    State(state): State<ApiState>,
    Json(req): Json<CompleteRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    // Build a document context from the request
    let doc_ctx = DocumentContext::from_raw_text(
        &req.prompt,
        &req.context,
        crate::document_context::DocKind::PlainText,
    );

    let (mode, _prompt) = CommandMode::from_prompt(&doc_ctx.prompt_text);
    let (target_backend, profile) = state.swarm_engine.route(&doc_ctx, &mode).await;

    let api_system = format!(
        "{} You are a helpful AI assistant. Answer the user's request directly and completely. \
         Output only the requested content — no meta-commentary, no preamble.",
        profile.system_directive
    );

    let resp = target_backend
        .complete(&api_system, &req.prompt)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let clean_resp = resp
        .strip_prefix("[REPLACE]")
        .unwrap_or(&resp)
        .trim()
        .to_string();

    Ok(Json(serde_json::json!({
        "text": clean_resp,
        "response": clean_resp,
        "content": clean_resp,
    })))
}

/// GET /app — MCP Tool: detect app
async fn get_app(State(state): State<ApiState>) -> Json<AppResponse> {
    let raw_text = state
        .uia
        .get_focused_text()
        .or_else(|_| state.uia.get_clipboard_text())
        .unwrap_or_default();

    let app_ctx = state.context_engine.capture(&raw_text);

    Json(AppResponse {
        process: app_ctx.process_name,
        environment: app_ctx.environment.label(),
    })
}

#[derive(Serialize)]
pub struct CapabilityInfo {
    pub id: String,
    pub name: String,
    pub capability: crate::plugin::DomainCapability,
}

/// GET /capabilities
pub async fn get_capabilities(State(state): State<ApiState>) -> Json<Vec<CapabilityInfo>> {
    let public_agents = state.swarm_engine.registry.public_agents();
    let capabilities = public_agents
        .iter()
        .map(|agent| CapabilityInfo {
            id: agent.id().to_string(),
            name: agent.name().to_string(),
            capability: agent.capability(),
        })
        .collect();
    Json(capabilities)
}

/// POST /agent — MCP Tool: switch agent
async fn set_agent(State(state): State<ApiState>, Json(req): Json<AgentRequest>) -> Json<()> {
    let mut lock = state.mcp_agent_override.lock().unwrap();
    *lock = Some(req.agent);
    Json(())
}

/// POST /materialize — Original overlay endpoint
async fn materialize(
    State(state): State<ApiState>,
    Json(req): Json<MaterializeRequest>,
) -> Result<Json<MaterializeResponse>, (StatusCode, String)> {
    let context = if let Some(ctx) = req.context {
        ctx
    } else {
        state
            .uia
            .get_focused_text()
            .or_else(|_| state.uia.get_clipboard_text())
            .unwrap_or_default()
    };

    if context.is_empty() {
        return Err((StatusCode::BAD_REQUEST, "No text context available".into()));
    }

    state.crdt.insert_human_text(&context);

    let system = state.crdt.get_system_prompt();
    let user = state.crdt.get_user_context();
    let suggestion = state
        .ai
        .complete(system, &user)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    state.crdt.insert_ai_text(&suggestion);

    let injector = state.injector.clone();
    let suggestion_clone = suggestion.clone();
    tokio::task::spawn_blocking(move || injector.type_text(&suggestion_clone));

    Ok(Json(MaterializeResponse {
        word_count: suggestion.split_whitespace().count(),
        char_count: suggestion.len(),
        suggestion,
    }))
}

/// POST /generate_image — MCP Tool: generate image via image pipeline
async fn generate_image(
    State(state): State<ApiState>,
    Json(req): Json<ImageGenerateRequest>,
) -> Result<Json<ImageGenerateResponse>, (StatusCode, String)> {
    use crate::document_context::DocumentContext;
    use crate::image_pipeline::{ImageGenerationConfig, ImageRouter};

    // Build a default doc context for routing
    let raw_text = state
        .uia
        .get_focused_text()
        .or_else(|_| state.uia.get_clipboard_text())
        .unwrap_or_default();
    let app_ctx = state.context_engine.capture(&raw_text);
    let doc_ctx = DocumentContext::from_raw_text(
        &app_ctx.prompt_text,
        &app_ctx.document_text,
        app_ctx.environment.to_doc_kind(),
    );

    let config = ImageGenerationConfig::default();
    let router = ImageRouter::new(config);

    match router.generate(&req.prompt, &doc_ctx).await {
        Ok(result) => Ok(Json(ImageGenerateResponse {
            status: "ok".into(),
            base64_data: result.base64_data,
            mime_type: result.mime_type,
            backend_used: result.backend_used,
        })),
        Err(e) => Err((
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Image generation failed: {e}"),
        )),
    }
}

#[derive(Deserialize)]
pub struct KamiExportRequest {
    pub content: String,
    pub format: String,
    pub output_path: String,
}

async fn kami_export(
    State(_state): State<ApiState>,
    Json(req): Json<KamiExportRequest>,
) -> (StatusCode, Json<()>) {
    let res = match req.format.as_str() {
        "pdf" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Pdf,
                req.content,
            )
            .await
        }
        "reveal" | "slides" | "revealjs" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Slides,
                req.content,
            )
            .await
        }
        "email" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Email,
                req.content,
            )
            .await
        }
        "linkedin" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::LinkedIn,
                req.content,
            )
            .await
        }
        "epub" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Epub,
                req.content,
            )
            .await
        }
        "book" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Book,
                req.content,
            )
            .await
        }
        "tweet" | "tweet-thread" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::TweetThread,
                req.content,
            )
            .await
        }
        "podcast" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Podcast,
                req.content,
            )
            .await
        }
        "podcast-local" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::PodcastLocal,
                req.content,
            )
            .await
        }
        "subtitles" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Subtitles,
                req.content,
            )
            .await
        }
        "quiz" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Quiz,
                req.content,
            )
            .await
        }
        "flashcards" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Flashcards,
                req.content,
            )
            .await
        }
        "mindmap" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Mindmap,
                req.content,
            )
            .await
        }
        "html" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::Html,
                req.content,
            )
            .await
        }
        "all" => {
            crate::kami_export::KamiExporter::execute(
                crate::kami_export::KamiCommand::All,
                req.content,
            )
            .await
        }
        _ => Err("Unsupported format".to_string()),
    };

    match res {
        Ok(_) => (StatusCode::OK, Json(())),
        Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, Json(())),
    }
}

async fn mobile_sync_post(
    State(state): State<ApiState>,
    Json(req): Json<MobileSyncRequest>,
) -> Json<MobileSyncResponse> {
    info!("📱 Mobile Bridge: Received sync from {}", req.device_id);

    // Store in memory for now, will eventually go to MemMachine
    let sync_id = uuid::Uuid::new_v4().to_string();

    // Inject into CRDT for real-time visibility in overlay
    state.crdt.insert_human_text(&format!(
        "\n--- Mobile Sync ({}) ---\n{}\n",
        req.device_id, req.content
    ));

    Json(MobileSyncResponse {
        status: "synced".into(),
        sync_id,
    })
}

pub async fn start_api_server(state: ApiState) {
    let app = Router::new()
        .route("/health", get(health))
        .route("/materialize", post(materialize))
        .route("/context", get(get_context))
        .route("/inject", post(inject))
        .route("/ask", post(ask))
        .route("/api/complete", post(complete))
        .route("/app", get(get_app))
        .route("/agent", post(set_agent))
        .route("/generate_image", post(generate_image))
        .route("/kami/export", post(kami_export))
        .route("/mobile/sync", post(mobile_sync_post))
        .route("/capabilities", get(get_capabilities))
        .with_state(state);

    let addr = format!("127.0.0.1:{PORT}");
    let listener = TcpListener::bind(&addr)
        .await
        .unwrap_or_else(|_| panic!("Failed to bind to {addr}"));

    info!("🌐 HTTP API listening on http://{}", addr);
    axum::serve(listener, app).await.unwrap();
}
