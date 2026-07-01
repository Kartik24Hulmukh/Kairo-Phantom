use crate::quality_gate::{IntegrityGateChecklist, MultiReviewerPipeline, SentinelHashDetector};
use tracing::{info, warn};

use futures::Future;
use tokio::sync::mpsc;

pub struct WritingPipeline;

impl WritingPipeline {
    pub async fn execute<F, Fut>(
        system_prompt: &str,
        context: &str,
        user_prompt: &str,
        generate_fn: F,
    ) -> Result<String, String>
    where
        F: Fn(String) -> Fut,
        Fut: Future<Output = String>,
    {
        let mut retries = 0;
        let sentinel = SentinelHashDetector::new();

        // Stage 1: Plan — use ONLY the user prompt + document context, NOT the full system_prompt
        // (system_prompt contains internal directives and security markers that confuse the model)
        info!("Pipeline Stage 1: Plan - Analyzing context and generating outline");
        let plan_prompt = if context.len() > 50 {
            format!(
                "Document context (first 500 chars):\n{}\n\nTask: {}",
                &context[..context.len().min(500)],
                user_prompt
            )
        } else {
            format!("Task: {user_prompt}")
        };
        let plan = generate_fn(plan_prompt).await;
        info!(
            "Plan: {}",
            if plan.len() > 100 {
                &plan[..100]
            } else {
                &plan
            }
        );

        while retries < 3 {
            // Stage 2: Write — build a clean prompt combining plan + user request
            info!("Pipeline Stage 2: Write - Attempt {}", retries + 1);

            // Build a clean user-facing prompt without exposing internal system_prompt
            let full_prompt = if plan.is_empty() || plan.len() < 10 {
                // Plan generation failed, just use the user prompt directly
                format!(
                    "Document context:\n{}\n\nRequest: {}\n\nProvide a complete, well-written response. Do not add meta-commentary.",
                    &context[..context.len().min(800)],
                    user_prompt
                )
            } else {
                format!(
                    "Plan:\n{}\n\nDocument context:\n{}\n\nRequest: {}\n\nNow write the complete response based on the plan above.",
                    &plan[..plan.len().min(400)],
                    &context[..context.len().min(500)],
                    user_prompt
                )
            };

            let raw_output = generate_fn(full_prompt).await;

            // Extract from <output> tags if present (optional — model may or may not include them)
            let clean_output = if let (Some(start), Some(end)) =
                (raw_output.find("<output>"), raw_output.find("</output>"))
            {
                if start < end {
                    raw_output[start + 8..end].trim().to_string()
                } else {
                    raw_output.trim().to_string()
                }
            } else {
                // No <output> tags — use the raw response directly (normal for most LLMs)
                raw_output.trim().to_string()
            };

            if clean_output.is_empty() {
                warn!("Pipeline Stage 2: Empty response from LLM. Retrying...");
                retries += 1;
                continue;
            }

            // Stage 3: Sentinel leak check
            info!("Pipeline Stage 3: Review - Checking for leakage");
            if let Err(e) = sentinel.scan_output(&clean_output) {
                warn!("Sentinel leak detected: {}. Retrying...", e);
                retries += 1;
                continue;
            }

            // Light integrity check — only block obvious problems
            if let Err(e) = IntegrityGateChecklist::check(&clean_output, context) {
                warn!("Integrity check: {}. Retrying...", e);
                retries += 1;
                continue;
            }

            // Stage 3b: Style quality review (advisory — warns but does not block production output)
            // This catches AI-phrase phrasing like "It is important to note", "delve into", etc.
            if let Err(reason) = MultiReviewerPipeline::review(&clean_output) {
                warn!("[WritingPipeline] Style reviewer advisory: {}", reason);
                // Non-blocking: we log the style issue but still return the output.
                // The LLM domain masters' JSON enforcement means this rarely fires
                // for structured JSON responses; it's most relevant for free-text fallback.
            }

            info!(
                "Pipeline Stage 4: Finalize - {} chars ready for injection",
                clean_output.len()
            );
            return Ok(clean_output);
        }

        Err("Pipeline failed after 3 retries.".to_string())
    }

    /// Streaming variant: executes the pipeline then sends tokens word-by-word via channel.
    /// This enables progressive UI rendering: the GRP can show text appearing in real time
    /// rather than waiting for the full batch response.
    ///
    /// The channel is closed automatically when all tokens have been sent.
    /// Caller should read from `rx` and inject tokens into the document progressively.
    pub async fn execute_streaming<F, Fut>(
        system_prompt: &str,
        context: &str,
        user_prompt: &str,
        generate_fn: F,
        token_tx: mpsc::Sender<String>,
    ) -> Result<String, String>
    where
        F: Fn(String) -> Fut,
        Fut: Future<Output = String>,
    {
        // Run full pipeline to get the complete validated response
        let full_response = Self::execute(system_prompt, context, user_prompt, generate_fn).await?;

        // Stream tokens word-by-word through the channel
        // Splitting on whitespace gives natural word boundaries for progressive injection.
        let words: Vec<&str> = full_response.split_whitespace().collect();
        let total = words.len();
        for (i, word) in words.iter().enumerate() {
            let token = if i < total - 1 {
                format!("{word} ") // add trailing space between words
            } else {
                word.to_string() // last word: no trailing space
            };
            // If receiver is dropped (e.g. user pressed Esc), stop streaming silently
            if token_tx.send(token).await.is_err() {
                info!("[WritingPipeline] Streaming cancelled: receiver dropped");
                break;
            }
        }
        // Channel closes automatically when token_tx is dropped at end of function
        Ok(full_response)
    }
}
