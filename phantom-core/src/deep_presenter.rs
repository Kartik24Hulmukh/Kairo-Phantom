//! Deep Presenter Integration — P2-A7
//! HTTP bridge to a local DeepPresenter-9B instance for research-grade PPTX generation.
//! When the user requests a presentation, Kairo delegates to DeepPresenter.

use anyhow::Result;
use serde::{Deserialize, Serialize};

const DEEPRESENTER_DEFAULT_URL: &str = "http://localhost:8765";

#[derive(Debug, Serialize)]
pub struct DeepPresenterRequest {
    pub topic: String,
    pub outline: Vec<String>,
    pub style: DeepPresenterStyle,
    pub slide_count: usize,
    pub output_format: &'static str, // "pptx" | "json"
}

#[derive(Debug, Serialize)]
pub struct DeepPresenterStyle {
    pub theme: String,                // "professional" | "minimal" | "bold"
    pub tone: String,                 // "formal" | "casual" | "technical"
    pub color_scheme: String,         // "blue" | "dark" | "brand"
    pub max_words_per_bullet: usize,  // enforce PPT concision (default: 25)
    pub max_bullets_per_slide: usize, // default: 5
}

impl Default for DeepPresenterStyle {
    fn default() -> Self {
        Self {
            theme: "professional".to_string(),
            tone: "formal".to_string(),
            color_scheme: "blue".to_string(),
            max_words_per_bullet: 25,
            max_bullets_per_slide: 5,
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct DeepPresenterResponse {
    pub status: String,
    pub slides: Vec<SlideContent>,
    pub pptx_base64: Option<String>,
    pub generation_time_ms: u64,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct SlideContent {
    pub title: String,
    pub bullets: Vec<String>,
    pub speaker_notes: Option<String>,
    pub slide_type: String, // "title" | "content" | "summary" | "agenda"
}

pub struct DeepPresenter {
    base_url: String,
    client: reqwest::Client,
}

impl DeepPresenter {
    pub fn new(base_url: Option<&str>) -> Self {
        Self {
            base_url: base_url.unwrap_or(DEEPRESENTER_DEFAULT_URL).to_string(),
            client: crate::config::get_client_builder()
                .build()
                .unwrap_or_default(),
        }
    }

    /// Check if DeepPresenter-9B is running locally.
    pub async fn is_available(&self) -> bool {
        self.client
            .get(format!("{}/health", self.base_url))
            .timeout(std::time::Duration::from_secs(2))
            .send()
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false)
    }

    /// Generate a full presentation from a topic + optional outline.
    /// Returns structured slide content for PPTX assembly.
    pub async fn generate(
        &self,
        topic: &str,
        outline: Vec<String>,
        style: DeepPresenterStyle,
    ) -> Result<Vec<SlideContent>> {
        let slide_count = if outline.is_empty() {
            8
        } else {
            outline.len() + 2
        };

        let request = DeepPresenterRequest {
            topic: topic.to_string(),
            outline,
            style,
            slide_count,
            output_format: "json",
        };

        let resp = self
            .client
            .post(format!("{}/generate", self.base_url))
            .json(&request)
            .timeout(std::time::Duration::from_secs(120))
            .send()
            .await?;

        let dp_resp: DeepPresenterResponse = resp.json().await?;
        tracing::info!(
            "🎨 DeepPresenter: {} slides in {}ms",
            dp_resp.slides.len(),
            dp_resp.generation_time_ms
        );
        Ok(dp_resp.slides)
    }

    /// Fallback: generate slide content locally using the swarm.
    /// Used when DeepPresenter-9B is not running.
    pub fn generate_fallback(topic: &str, outline: &[String]) -> Vec<SlideContent> {
        let mut slides = vec![SlideContent {
            title: topic.to_string(),
            bullets: vec![],
            speaker_notes: Some(format!("Opening slide for: {topic}")),
            slide_type: "title".to_string(),
        }];

        for (i, section) in outline.iter().enumerate() {
            slides.push(SlideContent {
                title: section.clone(),
                bullets: vec![
                    format!("Key point about {}", section),
                    "Supporting evidence and context".to_string(),
                    "Actionable takeaway".to_string(),
                ],
                speaker_notes: Some(format!(
                    "Section {} of {}: {}",
                    i + 1,
                    outline.len(),
                    section
                )),
                slide_type: "content".to_string(),
            });
        }

        slides.push(SlideContent {
            title: "Summary & Next Steps".to_string(),
            bullets: vec![
                "Key takeaways from today".to_string(),
                "Recommended actions".to_string(),
                "Questions?".to_string(),
            ],
            speaker_notes: Some("Closing slide".to_string()),
            slide_type: "summary".to_string(),
        });

        slides
    }

    /// Format slide content for text injection into an active PPT context.
    pub fn format_for_injection(slides: &[SlideContent]) -> String {
        let mut output = String::new();
        for slide in slides {
            output.push_str(&format!("## {}\n", slide.title));
            for bullet in &slide.bullets {
                // Enforce PPT concision: max 25 words
                let words: Vec<&str> = bullet.split_whitespace().collect();
                let trimmed = if words.len() > 25 {
                    format!("{}...", words[..25].join(" "))
                } else {
                    bullet.clone()
                };
                output.push_str(&format!("• {trimmed}\n"));
            }
            output.push('\n');
        }
        output
    }
}
