//! Kairo MCP Server — Phase 4 Distribution
//! Exposes Kairo's capabilities as an MCP server for Claude Code, Cursor, Goose, Windsurf.
//! Tools: kairo_read_context, kairo_ghost_write, kairo_generate_image, kairo_detect_app, kairo_ask

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::{self, BufRead, Write};

#[derive(Deserialize, Debug)]
struct JsonRpcRequest {
    #[allow(dead_code)]
    jsonrpc: String,
    id: Option<Value>,
    method: String,
    #[serde(default)]
    params: Value,
}

#[derive(Serialize)]
struct JsonRpcResponse {
    jsonrpc: String,
    id: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<Value>,
}

fn respond(id: Value, result: Option<Value>, error: Option<Value>) {
    let resp = JsonRpcResponse {
        jsonrpc: "2.0".to_string(),
        id,
        result,
        error,
    };
    let line = serde_json::to_string(&resp).unwrap_or_default();
    println!("{line}");
    io::stdout().flush().ok();
}

fn ok(id: Value, result: Value) {
    respond(id, Some(result), None);
}

fn err(id: Value, msg: &str) {
    respond(id, None, Some(json!({"code": -32000, "message": msg})));
}

/// Tool: kairo_read_context — reads the currently focused window's text via HTTP API
async fn kairo_read_context(id: Value, _args: &Value) {
    let client = reqwest::Client::new();
    match client.get("http://localhost:7437/context").send().await {
        Ok(r) => {
            let text = r.text().await.unwrap_or_default();
            ok(id, json!({"context": text}));
        }
        Err(e) => err(id, &format!("Failed to read context: {e}")),
    }
}

/// Tool: kairo_ghost_write — inject text into the active window
async fn kairo_ghost_write(id: Value, args: &Value) {
    let text = args.get("text").and_then(|v| v.as_str()).unwrap_or("");
    if text.is_empty() {
        err(id, "text argument required");
        return;
    }

    let client = reqwest::Client::new();
    let payload = json!({"text": text});

    match client
        .post("http://localhost:7437/inject")
        .json(&payload)
        .send()
        .await
    {
        Ok(r) if r.status().is_success() => {
            ok(id, json!({"status": "injected", "chars": text.len()}))
        }
        Ok(r) => err(id, &format!("Inject failed: HTTP {}", r.status())),
        Err(e) => err(id, &format!("Inject error: {e}")),
    }
}

/// Tool: kairo_detect_app — returns the currently active app fingerprint
async fn kairo_detect_app(id: Value, _args: &Value) {
    let client = reqwest::Client::new();
    match client.get("http://localhost:7437/app").send().await {
        Ok(r) => {
            let data: Value = r.json().await.unwrap_or(json!({}));
            ok(id, data);
        }
        Err(e) => err(id, &format!("Failed to detect app: {e}")),
    }
}

/// Tool: kairo_batch_execute — chain multiple operations (MCP Infrastructure B2)
async fn kairo_batch_execute(id: Value, args: &Value) {
    let operations = args.get("operations").and_then(|v| v.as_array());
    if operations.is_none() {
        err(id, "operations array required");
        return;
    }

    let mut results = Vec::new();
    let client = reqwest::Client::new();

    for op in operations.unwrap() {
        let op_name = op.get("op").and_then(|v| v.as_str()).unwrap_or("");
        let op_args = op.get("args").unwrap_or(&Value::Null);

        // Execute operation sequentially via HTTP but in a single MCP round trip
        let res = match op_name {
            "read_context" => client
                .get("http://localhost:7437/context")
                .send()
                .await
                .and_then(|r| r.error_for_status())
                .map(|_| json!({"status": "ok"}))
                .map_err(|e| e.to_string()),
            "detect_app" => client
                .get("http://localhost:7437/app")
                .send()
                .await
                .and_then(|r| r.error_for_status())
                .map(|_| json!({"status": "ok"}))
                .map_err(|e| e.to_string()),
            "ghost_write" => client
                .post("http://localhost:7437/inject")
                .json(op_args)
                .send()
                .await
                .and_then(|r| r.error_for_status())
                .map(|_| json!({"status": "ok"}))
                .map_err(|e| e.to_string()),
            _ => Err("unknown op".to_string()),
        };

        match res {
            Ok(v) => results.push(json!({"op": op_name, "success": true, "result": v})),
            Err(e) => {
                results.push(json!({"op": op_name, "success": false, "error": e.to_string()}))
            }
        }
    }

    ok(id, json!({"batch_results": results}));
}

/// Tool: kairo_ask — full Alt+M round-trip programmatically
async fn kairo_ask(id: Value, args: &Value) {
    let prompt = args.get("prompt").and_then(|v| v.as_str()).unwrap_or("");
    let agent = args.get("agent").and_then(|v| v.as_str()).unwrap_or("auto");

    if prompt.is_empty() {
        err(id, "prompt argument required");
        return;
    }

    let client = reqwest::Client::new();
    let payload = json!({"prompt": prompt, "agent": agent});

    match client
        .post("http://localhost:7437/ask")
        .json(&payload)
        .send()
        .await
    {
        Ok(r) => {
            let data: Value = r.json().await.unwrap_or(json!({}));
            ok(id, data);
        }
        Err(e) => err(id, &format!("Ask failed: {e}")),
    }
}

/// Tool: kairo_generate_image — generate image via the image pipeline
async fn kairo_generate_image(id: Value, args: &Value) {
    let prompt = args.get("prompt").and_then(|v| v.as_str()).unwrap_or("");
    let backend = args
        .get("backend")
        .and_then(|v| v.as_str())
        .unwrap_or("auto");

    if prompt.is_empty() {
        err(id, "prompt argument required");
        return;
    }

    let client = reqwest::Client::new();
    let payload = json!({"prompt": prompt, "backend": backend});

    match client
        .post("http://localhost:7437/generate_image")
        .json(&payload)
        .send()
        .await
    {
        Ok(r) => {
            let data: Value = r.json().await.unwrap_or(json!({}));
            ok(id, data);
        }
        Err(e) => err(id, &format!("Image generation failed: {e}")),
    }
}

/// Tool: kairo_generate_slide — generate a full PPTX deck from a topic via PPTX bridge
async fn kairo_generate_slide(id: Value, args: &Value) {
    let topic = args.get("topic").and_then(|v| v.as_str()).unwrap_or("");
    let theme = args
        .get("theme")
        .and_then(|v| v.as_str())
        .unwrap_or("corporate");
    let slide_count = args
        .get("slide_count")
        .and_then(|v| v.as_u64())
        .unwrap_or(6);

    if topic.is_empty() {
        err(id, "topic argument required");
        return;
    }

    let client = reqwest::Client::new();

    // Step 1: Ask Kairo to generate slide specs
    let ask_payload = serde_json::json!({
        "prompt": format!(
            "Generate {} slides for a professional presentation about '{}'. \
            Output JSON array with objects: {{title, content, layout(title/content/blank), notes}}. \
            Layout 'title' for slide 0, 'content' for rest. JSON only, no markdown.",
            slide_count, topic
        ),
        "agent": "design"
    });

    let slide_specs = match client
        .post("http://localhost:7437/ask")
        .json(&ask_payload)
        .send()
        .await
    {
        Ok(r) => {
            let data: serde_json::Value = r.json().await.unwrap_or(serde_json::json!({}));
            let response_text = data["response"].as_str().unwrap_or("[]");
            // Extract JSON array from response
            if let Ok(specs) = serde_json::from_str::<serde_json::Value>(response_text) {
                specs
            } else {
                // Fallback: minimal 4-slide deck
                serde_json::json!([
                    {"title": topic, "content": "", "layout": "title", "notes": ""},
                    {"title": "Overview", "content": format!("Key points about {topic}"), "layout": "content", "notes": ""},
                    {"title": "Details", "content": "Expand on the main ideas here", "layout": "content", "notes": ""},
                    {"title": "Conclusion", "content": format!("Summary and next steps for {topic}"), "layout": "content", "notes": ""}
                ])
            }
        }
        Err(e) => {
            err(id, &format!("Failed to generate slide specs: {e}"));
            return;
        }
    };

    // Step 2: Create PPTX via bridge
    let output_path = format!(
        "{}/kairo_{}.pptx",
        std::env::temp_dir().to_string_lossy(),
        topic.chars().take(20).collect::<String>().replace(' ', "_")
    );

    let pptx_payload = serde_json::json!({
        "topic": topic,
        "slide_specs": slide_specs,
        "output_path": output_path
    });

    match client
        .post("http://localhost:7437/pptx_bridge/generate_ai_presentation")
        .json(&pptx_payload)
        .send()
        .await
    {
        Ok(r) => {
            let data: serde_json::Value = r.json().await.unwrap_or(serde_json::json!({}));
            ok(
                id,
                serde_json::json!({
                    "status": "ok",
                    "topic": topic,
                    "theme": theme,
                    "output_path": output_path,
                    "slide_count": slide_specs.as_array().map(|a| a.len()).unwrap_or(0),
                    "pptx_result": data
                }),
            );
        }
        Err(_) => {
            // Bridge not running — return specs for manual use
            ok(
                id,
                serde_json::json!({
                    "status": "specs_only",
                    "topic": topic,
                    "slide_specs": slide_specs,
                    "note": "PPTX bridge not running. Start kairo-phantom and ensure office-pptx-bridge is spawned."
                }),
            );
        }
    }
}

/// Tool: kairo_generate_image_inject — generate image and inject into active document
async fn kairo_generate_image_inject(id: Value, args: &Value) {
    let prompt = args.get("prompt").and_then(|v| v.as_str()).unwrap_or("");
    let backend = args
        .get("backend")
        .and_then(|v| v.as_str())
        .unwrap_or("auto");

    if prompt.is_empty() {
        err(id, "prompt argument required");
        return;
    }

    let client = reqwest::Client::new();
    let payload = serde_json::json!({"prompt": prompt, "backend": backend, "inject": true});

    match client
        .post("http://localhost:7437/generate_image")
        .json(&payload)
        .send()
        .await
    {
        Ok(r) => {
            let data: serde_json::Value = r.json().await.unwrap_or(serde_json::json!({}));
            ok(
                id,
                serde_json::json!({
                    "status": data["status"],
                    "backend_used": data["backend_used"],
                    "mime_type": data["mime_type"],
                    "injection_method": data.get("injection_method").unwrap_or(&serde_json::json!("clipboard")),
                    "note": "Image has been copied to clipboard. Use Ctrl+V to paste."
                }),
            );
        }
        Err(e) => err(id, &format!("Image generation failed: {e}")),
    }
}

/// Tool: kairo_list_agents — list all available swarm agents
async fn kairo_list_agents(id: Value, _args: &Value) {
    ok(
        id,
        serde_json::json!({
            "agents": [
                {"id": "auto", "name": "Auto-Router (Swarm Brain)", "description": "Automatically selects the best agent based on document type and prompt"},
                {"id": "design", "name": "Design & Media", "description": "PowerPoint, Figma, Canva, visual layouts, slide structures"},
                {"id": "reasoning", "name": "Reasoning & Logic", "description": "Code, calculations, debugging, terminal commands"},
                {"id": "content", "name": "Content All-Rounder", "description": "Word documents, general writing, formatting, professional prose"},
                {"id": "student", "name": "Student Tutor", "description": "Beginner-friendly explanations, guided writing, study notes"},
                {"id": "engineer", "name": "Engineer", "description": "Technical documentation, architecture, README, conventional commits"},
                {"id": "data", "name": "Data Analyst", "description": "Excel formulas, spreadsheets, data summaries, pivot tables"},
                {"id": "image", "name": "Image Generation", "description": "Generate [IMAGE: prompt] tags for AI image creation"},
                {"id": "sales", "name": "Sales & Marketing", "description": "Cold email, proposals, pitch decks, CRM notes"},
                {"id": "medical", "name": "Medical Documentation", "description": "SOAP notes, clinical summaries, ICD-10 coding"},
                {"id": "legal", "name": "Legal Documents", "description": "Contracts, NDAs, agreements, legal analysis"},
                {"id": "academic", "name": "Academic Writing", "description": "Research papers, citations (APA/MLA/Chicago), abstracts"},
                {"id": "hr", "name": "HR & Talent", "description": "Job descriptions, performance reviews, offer letters, policies"},
                {"id": "marketing", "name": "Marketing Content", "description": "Blog posts, social copy, SEO, landing pages, ad copy"},
                {"id": "product", "name": "Product Management", "description": "PRDs, user stories, OKRs, roadmaps, sprint planning"}
            ]
        }),
    )
}

fn list_tools() -> Value {
    json!({
            "tools": [
                {
                    "name": "kairo_read_context",
                    "description": "Read the currently focused window's text and document context from Kairo Phantom",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                },
                {
                    "name": "kairo_ghost_write",
                    "description": "Inject text directly into the currently active window via Kairo Phantom's ghost-typing engine",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Text to inject into the active window"}
                        },
                        "required": ["text"]
                    }
                },
                {
                    "name": "kairo_detect_app",
                    "description": "Detect the currently active application and its document type",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                },
                {
                    "name": "kairo_ask",
                    "description": "Run a full Kairo AI round-trip: read context, route to agent, stream response, inject",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "The user's instruction or request"},
                            "agent": {"type": "string", "description": "Agent override: auto, design, reasoning, content, code (default: auto)"}
                        },
                        "required": ["prompt"]
                    }
                },
                {
                    "name": "kairo_generate_image",
                    "description": "Generate an image using Kairo's image pipeline (gpt-image-1 or local Stable Diffusion)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "Image generation prompt"},
                            "backend": {"type": "string", "description": "Backend: auto, cloud, local (default: auto)"}
                        },
                        "required": ["prompt"]
                    }
                },
                {
                    "name": "kairo_generate_slide",
                    "description": "Generate a full PowerPoint presentation deck from a topic using Kairo's AI + PPTX bridge",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "Presentation topic"},
                            "slide_count": {"type": "integer", "description": "Number of slides (default: 6)"},
                            "theme": {"type": "string", "description": "Theme: corporate, dark, light, minimal, ocean, forest (default: corporate)"}
                        },
                        "required": ["topic"]
                    }
                },
                {
                    "name": "kairo_generate_image_inject",
                    "description": "Generate an image and automatically inject it into the active document (clipboard or Word/PPTX)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "Image generation prompt"},
                            "backend": {"type": "string", "description": "Backend: auto, cloud, local, gemini (default: auto)"}
                        },
                        "required": ["prompt"]
                    }
                },
                {
                    "name": "kairo_batch_execute",
                    "description": "Execute multiple Kairo operations in a single round-trip (e.g. read_context + detect_app + ghost_write)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "operations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "op": {"type": "string", "description": "Operation: read_context, detect_app, ghost_write"},
                                        "args": {"type": "object", "description": "Arguments for the operation"}
                                    },
                                    "required": ["op"]
                                }
                            }
                        },
                        "required": ["operations"]
                    }
                },
                {
                    "name": "kairo_list_agents",
                    "description": "List all available Kairo swarm agents with their IDs and descriptions",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                }
            ,
            {"name": "kairo_word_process", "description": "Word/DOCX domain: extract context, generate response, apply operations.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_excel_process", "description": "Excel/spreadsheet domain: extract context, generate formulas, validate.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_pptx_process", "description": "PowerPoint domain: extract slide context, generate content.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_pdf_process", "description": "PDF domain: extract text, tables, form fields.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["file_path"]}},
            {"name": "kairo_legal_process", "description": "Legal domain: CUAD clause extraction, citation graph, redline.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_design_process", "description": "Design domain: Figma/tldraw bridge, canvas operations.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_code_process", "description": "Code domain: tree-sitter parsing, code graph, analysis.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_media_process", "description": "Media domain: image processing, embeddings, transcription.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_browser_process", "description": "Browser domain: web page context, automation guidance.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_terminal_process", "description": "Terminal domain: safe command generation, shell context.", "inputSchema": {"type": "object", "properties": {"instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_email_process", "description": "Email domain: drafting, subject validation, PII redaction.", "inputSchema": {"type": "object", "properties": {"instruction": {"type": "string"}}, "required": ["instruction"]}},
            {"name": "kairo_notes_process", "description": "Notes domain: Obsidian/Logseq/Markdown management.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["instruction"]}}
    ]
        })
}

#[tokio::main]
async fn main() {
    eprintln!("kairo-mcp v0.3.0 started (stdio transport)");
    eprintln!("Make sure kairo-phantom is running on http://localhost:7437");

    let stdin = io::stdin();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l.trim().to_string(),
            Err(_) => break,
        };

        if line.is_empty() {
            continue;
        }

        let req: JsonRpcRequest = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                eprintln!("JSON parse error: {e}");
                continue;
            }
        };

        let id = req.id.clone().unwrap_or(Value::Null);
        let args = req.params.get("arguments").unwrap_or(&Value::Null).clone();

        match req.method.as_str() {
            "initialize" => {
                ok(
                    id,
                    json!({
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "kairo-phantom-mcp",
                            "version": "0.3.0"
                        }
                    }),
                );
            }
            "tools/list" => {
                ok(id, list_tools());
            }
            "tools/call" => {
                let tool_name = req
                    .params
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                match tool_name {
                    "kairo_read_context" => kairo_read_context(id, &args).await,
                    "kairo_ghost_write" => kairo_ghost_write(id, &args).await,
                    "kairo_detect_app" => kairo_detect_app(id, &args).await,
                    "kairo_ask" => kairo_ask(id, &args).await,
                    "kairo_generate_image" => kairo_generate_image(id, &args).await,
                    "kairo_generate_slide" => kairo_generate_slide(id, &args).await,
                    "kairo_generate_image_inject" => kairo_generate_image_inject(id, &args).await,
                    "kairo_batch_execute" => kairo_batch_execute(id, &args).await,
                    "kairo_list_agents" => kairo_list_agents(id, &args).await,
                    // 12 Domain Tools — route through sidecar HTTP API
                    "kairo_word_process"
                    | "kairo_excel_process"
                    | "kairo_pptx_process"
                    | "kairo_pdf_process"
                    | "kairo_legal_process"
                    | "kairo_design_process"
                    | "kairo_code_process"
                    | "kairo_media_process"
                    | "kairo_browser_process"
                    | "kairo_terminal_process"
                    | "kairo_email_process"
                    | "kairo_notes_process" => {
                        let instruction = args
                            .get("instruction")
                            .and_then(|v| v.as_str())
                            .unwrap_or("");
                        let file_path = args
                            .get("file_path")
                            .or(args.get("url"))
                            .and_then(|v| v.as_str())
                            .unwrap_or("");
                        let domain = tool_name
                            .strip_prefix("kairo_")
                            .unwrap_or("")
                            .strip_suffix("_process")
                            .unwrap_or("");
                        let prompt = format!(
                            "Domain: {domain}\nFile: {file_path}\nInstruction: {instruction}"
                        );
                        let client = reqwest::Client::new();
                        match client
                            .post("http://localhost:7437/ask")
                            .json(&json!({"prompt": prompt}))
                            .send()
                            .await
                        {
                            Ok(r) => {
                                let text = r.text().await.unwrap_or_default();
                                ok(
                                    id,
                                    json!({"content": [{"type": "text", "text": format!("Domain '{}' tool executed.\nResponse: {}", domain, text)}]}),
                                );
                            }
                            Err(e) => {
                                ok(
                                    id,
                                    json!({"content": [{"type": "text", "text": format!("Domain '{}' tool called but sidecar not reachable: {}. Start sidecar with: cd kairo-sidecar && python sidecar.py", domain, e)}]}),
                                );
                            }
                        }
                    }
                    other => err(id, &format!("Unknown tool: {other}")),
                }
            }
            other => {
                err(id, &format!("Unknown method: {other}"));
            }
        }
    }
}
