use crate::AgentManifest;
use notify::{Event, RecursiveMode, Watcher};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, RwLock};

pub struct AgentRegistry {
    agents_dir: PathBuf,
    agents: Arc<RwLock<HashMap<String, AgentManifest>>>,
}

impl AgentRegistry {
    pub fn new(agents_dir: PathBuf) -> Self {
        let registry = Self {
            agents_dir: agents_dir.clone(),
            agents: Arc::new(RwLock::new(HashMap::new())),
        };
        registry.scan();
        registry
    }

    pub fn scan(&self) {
        let mut new_agents = HashMap::new();
        if let Ok(entries) = fs::read_dir(&self.agents_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let manifest_path = path.join("manifest.toml");
                    if manifest_path.exists() {
                        if let Ok(content) = fs::read_to_string(&manifest_path) {
                            if let Ok(manifest) = toml::from_str::<AgentManifest>(&content) {
                                new_agents.insert(manifest.agent.id.clone(), manifest);
                            }
                        }
                    }
                }
            }
        }
        let mut lock = self.agents.write().unwrap();
        *lock = new_agents;
    }

    pub fn get_agents(&self) -> HashMap<String, AgentManifest> {
        self.agents.read().unwrap().clone()
    }

    pub fn start_hot_reload(&self) {
        let agents_ref = self.agents.clone();
        let dir = self.agents_dir.clone();

        std::thread::spawn(move || {
            let dir_clone = dir.clone();
            let mut watcher = notify::recommended_watcher(move |res: notify::Result<Event>| {
                match res {
                    Ok(_event) => {
                        // Rescan entirely on any change for simplicity
                        let mut new_agents = HashMap::new();
                        if let Ok(entries) = fs::read_dir(&dir_clone) {
                            for entry in entries.flatten() {
                                let path = entry.path();
                                if path.is_dir() {
                                    let manifest_path = path.join("manifest.toml");
                                    if manifest_path.exists() {
                                        if let Ok(content) = fs::read_to_string(&manifest_path) {
                                            if let Ok(manifest) =
                                                toml::from_str::<AgentManifest>(&content)
                                            {
                                                new_agents
                                                    .insert(manifest.agent.id.clone(), manifest);
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        let mut lock = agents_ref.write().unwrap();
                        *lock = new_agents;
                    }
                    Err(e) => println!("watch error: {e:?}"),
                }
            })
            .unwrap();

            watcher.watch(&dir, RecursiveMode::Recursive).unwrap();

            // Block thread
            loop {
                std::thread::sleep(std::time::Duration::from_secs(60));
            }
        });
    }
}
