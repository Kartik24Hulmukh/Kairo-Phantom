use super::IntegrationAdapter;
use anyhow::{anyhow, Result};
use async_trait::async_trait;

pub struct SlackAdapter {
    token: Option<String>,
}

impl Default for SlackAdapter {
    fn default() -> Self {
        Self::new()
    }
}

impl SlackAdapter {
    pub fn new() -> Self {
        Self { token: None }
    }

    fn get_token(&self) -> Result<String> {
        self.token
            .clone()
            .or_else(|| {
                // Mock: Get from env or config
                std::env::var("SLACK_BOT_TOKEN").ok()
            })
            .ok_or_else(|| anyhow!("Slack token not configured"))
    }
}

#[async_trait]
impl IntegrationAdapter for SlackAdapter {
    fn id(&self) -> &'static str {
        "slack"
    }

    async fn is_available(&self) -> bool {
        self.get_token().is_ok()
    }

    async fn get_deep_context(&self) -> Result<String> {
        let _token = self.get_token()?;

        // Mock Slack API call to fetch channel info
        Ok(
            "Slack Channel: #engineering\nUsers Online: 12\nRecent Topics: Kairo Phantom Release"
                .to_string(),
        )
    }

    async fn execute_action(&self, action: &str, data: &str) -> Result<()> {
        let _token = self.get_token()?;

        match action {
            "post_message" => {
                // Mock Slack API call to post message
                println!("Slack: Posting message: {data}");
                Ok(())
            }
            _ => Err(anyhow!("Unsupported action: {action}")),
        }
    }
}
