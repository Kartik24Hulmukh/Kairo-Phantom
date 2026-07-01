use crate::memory_store::MemoryStore;
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;
use tokio::time::sleep;
use tracing::{info, warn};

pub async fn start_document_scanner(
    mem_store: Arc<std::sync::Mutex<(MemoryStore, crate::memory::KairoMemory)>>,
) {
    info!("📂 Background document scanner started. Monitoring ~/.kairo-phantom/inbox");

    let mut inbox_path = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
    inbox_path.push(".kairo-phantom");
    inbox_path.push("inbox");

    // Create inbox if it doesn't exist
    if let Err(e) = fs::create_dir_all(&inbox_path) {
        warn!("Failed to create inbox directory: {}", e);
        return;
    }

    loop {
        match fs::read_dir(&inbox_path) {
            Ok(entries) => {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_file() {
                        info!(
                            "📄 Background Worker: Processing new document: {:?}",
                            path.file_name()
                        );

                        // Heuristic learning: add to memory as 'background_knowledge'
                        if let Ok(mut store_lock) = mem_store.lock() {
                            let (_, ref mut memory) = *store_lock;
                            let filename = path
                                .file_name()
                                .unwrap_or_default()
                                .to_string_lossy()
                                .to_string();
                            memory.app_bias.insert(
                                filename.clone(),
                                format!("Context from background document: {filename}"),
                            );
                        }

                        // In a full implementation, we'd use KreuzbergExtractor here
                        // For now, we move it to a 'processed' folder
                        let mut processed_path = inbox_path.clone();
                        processed_path.push("processed");
                        fs::create_dir_all(&processed_path).ok();

                        let mut dest = processed_path.clone();
                        dest.push(path.file_name().unwrap());

                        if let Err(e) = fs::rename(&path, &dest) {
                            warn!("Failed to move processed file: {}", e);
                        }
                    }
                }
            }
            Err(e) => warn!("Failed to read inbox: {}", e),
        }

        sleep(Duration::from_secs(60)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::KairoMemory;
    use crate::memory_store::MemoryStore;
    use std::sync::{Arc, Mutex};

    #[tokio::test]
    async fn test_background_worker_init() {
        let path = std::env::temp_dir().join("kairo_test_mem.db");
        let store = MemoryStore::new(path);
        let memory = KairoMemory::default();
        let mem_store = Arc::new(Mutex::new((store, memory)));

        // Just test that the directory is created and the loop can start
        let handle = tokio::spawn(async move {
            start_document_scanner(mem_store).await;
        });

        sleep(Duration::from_millis(500)).await;
        handle.abort();

        let mut inbox = dirs::home_dir().expect("home_dir must exist in test environment");
        inbox.push(".kairo-phantom/inbox");
        assert!(inbox.exists());
    }
}
