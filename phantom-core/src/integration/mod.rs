use anyhow::Result;
use async_trait::async_trait;

/// The IntegrationAdapter trait defines the interface for deep app-specific integrations.
/// Unlike the general AccessibilityReader, these adapters may use app-specific APIs,
/// file system structures, or local plugins to provide richer context or control.
#[async_trait]
pub trait IntegrationAdapter: Send + Sync {
    /// The unique identifier for this integration (e.g., "obsidian", "notion").
    fn id(&self) -> &'static str;

    /// Checks if the target application is available and accessible.
    async fn is_available(&self) -> bool;

    /// Extracts deep context from the application (e.g., local vault links, database metadata).
    async fn get_deep_context(&self) -> Result<String>;

    /// Executes an action in the target application (e.g., creating a new note, appending to a block).
    async fn execute_action(&self, action: &str, data: &str) -> Result<()>;
}

pub mod notion;
pub mod obsidian;
pub mod slack;

/// A registry of available integration adapters.
pub struct IntegrationManager {
    adapters: Vec<Box<dyn IntegrationAdapter>>,
}

impl Default for IntegrationManager {
    fn default() -> Self {
        Self::new()
    }
}

impl IntegrationManager {
    pub fn new() -> Self {
        Self {
            adapters: vec![
                Box::new(obsidian::ObsidianAdapter::new()),
                Box::new(notion::NotionAdapter::new()),
                Box::new(slack::SlackAdapter::new()),
            ],
        }
    }

    pub async fn get_adapter(&self, id: &str) -> Option<&dyn IntegrationAdapter> {
        for adapter in &self.adapters {
            if adapter.id() == id && adapter.is_available().await {
                return Some(adapter.as_ref());
            }
        }
        None
    }
}
