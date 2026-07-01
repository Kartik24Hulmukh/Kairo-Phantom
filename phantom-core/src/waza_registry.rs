//! Waza Skills Registry — P3-A2
//! `kairo skill add <github-url>` — Install skills from GitHub-hosted registry.
//! Manages skill manifests, validates TOML, sandboxes WASM plugins.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const REGISTRY_URL: &str =
    "https://raw.githubusercontent.com/KairoPhantom/kairo-skills-registry/main/registry.json";

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct SkillManifest {
    pub id: String,
    pub name: String,
    pub version: String,
    pub description: String,
    pub author: String,
    pub category: String, // "legal" | "medical" | "developer" | "finance" | "general"
    pub skill_md_url: String,
    pub wasm_url: Option<String>,
    pub signature: Option<String>, // Ed25519 base64 sig of wasm bytes
    pub requires_kairo: String,    // min Kairo version
    pub tags: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct SkillRegistry {
    pub version: String,
    pub skills: Vec<SkillManifest>,
}

pub struct WazaSkillManager {
    skills_dir: PathBuf,
}

impl WazaSkillManager {
    pub fn new() -> Self {
        let skills_dir = dirs::home_dir()
            .unwrap_or_default()
            .join(".kairo-phantom")
            .join("skills");
        std::fs::create_dir_all(&skills_dir).ok();
        Self { skills_dir }
    }
}

impl Default for WazaSkillManager {
    fn default() -> Self {
        Self::new()
    }
}

impl WazaSkillManager {
    /// Add a skill from a GitHub URL: `kairo skill add <url>`
    pub async fn add_skill(&self, url: &str, allow_unsigned: bool) -> Result<SkillManifest> {
        // Fetch the skill's manifest TOML
        let client = crate::config::get_client_builder()
            .build()
            .unwrap_or_default();

        // If URL points to a SKILL.md, derive manifest URL
        let manifest_url = if url.ends_with("SKILL.md") {
            url.replace("SKILL.md", "manifest.toml")
        } else if url.ends_with("manifest.toml") {
            url.to_string()
        } else {
            format!("{}/manifest.toml", url.trim_end_matches('/'))
        };

        let manifest_text = client
            .get(&manifest_url)
            .timeout(std::time::Duration::from_secs(30))
            .send()
            .await?
            .text()
            .await?;

        let manifest: SkillManifest = toml::from_str(&manifest_text)?;

        // Download SKILL.md
        let skill_md = client
            .get(&manifest.skill_md_url)
            .timeout(std::time::Duration::from_secs(30))
            .send()
            .await?
            .text()
            .await?;

        // Create skill directory
        let skill_dir = self.skills_dir.join(&manifest.id);
        std::fs::create_dir_all(&skill_dir)?;
        std::fs::write(skill_dir.join("SKILL.md"), &skill_md)?;
        std::fs::write(skill_dir.join("manifest.toml"), &manifest_text)?;

        // If WASM plugin exists, download and verify signature
        if let Some(wasm_url) = &manifest.wasm_url {
            let wasm_bytes = client
                .get(wasm_url)
                .timeout(std::time::Duration::from_secs(60))
                .send()
                .await?
                .bytes()
                .await?;

            if let Some(sig) = &manifest.signature {
                tracing::info!("🔐 Verifying Ed25519 signature for {}", manifest.id);
                Self::verify_wasm_signature(&wasm_bytes, sig)?;
            } else if allow_unsigned {
                tracing::warn!(
                    "⚠️  Skill '{}' has no WASM signature — using anyway (--allow-unsigned passed)",
                    manifest.id
                );
            } else {
                anyhow::bail!("WASM signature verification failed: skill is unsigned but signatures are required");
            }

            std::fs::write(skill_dir.join("plugin.wasm"), &wasm_bytes)?;
        }

        tracing::info!(
            "✅ Skill installed: {} v{}",
            manifest.name,
            manifest.version
        );
        println!(
            "✅ Installed: {} v{} by {}",
            manifest.name, manifest.version, manifest.author
        );
        println!("   Category: {}", manifest.category);
        println!("   {}", manifest.description);

        Ok(manifest)
    }

    /// List all installed skills.
    pub fn list_installed(&self) -> Vec<SkillManifest> {
        let mut skills = Vec::new();
        if let Ok(entries) = std::fs::read_dir(&self.skills_dir) {
            for entry in entries.flatten() {
                let manifest_path = entry.path().join("manifest.toml");
                if let Ok(content) = std::fs::read_to_string(&manifest_path) {
                    if let Ok(m) = toml::from_str::<SkillManifest>(&content) {
                        skills.push(m);
                    }
                }
            }
        }
        skills
    }

    /// Remove an installed skill.
    pub fn remove_skill(&self, skill_id: &str) -> Result<()> {
        let skill_dir = self.skills_dir.join(skill_id);
        if skill_dir.exists() {
            std::fs::remove_dir_all(&skill_dir)?;
            println!("✅ Removed skill: {skill_id}");
        } else {
            anyhow::bail!("Skill '{skill_id}' not found");
        }
        Ok(())
    }

    /// Scaffold a new skill: `kairo skill new <name>`
    /// Writes to ~/.kairo-phantom/skills/<name>/ so `kairo skill list` finds it immediately.
    pub fn scaffold_skill(name: &str) -> Result<PathBuf> {
        let safe_name = name.to_lowercase().replace(' ', "-");

        // Write to ~/.kairo-phantom/skills/ so `kairo skill list` finds it immediately.
        // Falls back to ./skills/ in CI / test environments where $HOME is unavailable.
        let skills_base = dirs::home_dir()
            .map(|h| h.join(".kairo-phantom").join("skills"))
            .unwrap_or_else(|| PathBuf::from("skills"));

        let skill_dir = skills_base.join(&safe_name);
        std::fs::create_dir_all(&skill_dir)?;

        // SKILL.md template
        std::fs::write(
            skill_dir.join("SKILL.md"),
            format!(
                "# {name}\n\n## What this skill does\n\nDescribe your skill here.\n\n\
             ## Activation\n\nThis skill activates when the user types:\n\n\
             ```\n// {safe_name}: <your prompt here>\n```\n\n\
             ## System Prompt\n\n```\nYou are a specialist in...\n```\n\n\
             ## Examples\n\n- Input: `// {safe_name}: improve tone`\n- Output: ...\n"
            ),
        )?;

        // manifest.toml template (valid TOML, parseable by list_installed)
        std::fs::write(
            skill_dir.join("manifest.toml"),
            format!(
                r#"id = "{safe_name}"
name = "{name}"
version = "0.1.0"
description = "A Kairo skill for ..."
author = "Your Name"
category = "general"
skill_md_url = "https://github.com/YOUR/REPO/raw/main/skills/{safe_name}/SKILL.md"
requires_kairo = "0.3.0"
tags = ["custom"]
"#
            ),
        )?;

        // Test harness (KMB-1 compatible)
        std::fs::write(
            skill_dir.join("test.toml"),
            format!(
                r#"# KMB-1 compatible test cases for {name}
[[tests]]
input = "sample input that triggers this skill"
expected_contains = ["expected keyword in output"]
max_words = 100
"#
            ),
        )?;

        println!("✅ Scaffolded skill: {}", skill_dir.display());
        println!(
            "   Edit {} to define your skill's behavior.",
            skill_dir.join("SKILL.md").display()
        );
        println!(
            "   Edit {} to fill in metadata.",
            skill_dir.join("manifest.toml").display()
        );
        println!("   Run: kairo skill list   (to see it appear)");
        println!("   Run: kairo skill test {safe_name} to validate");

        Ok(skill_dir)
    }

    fn verify_wasm_signature(wasm_bytes: &[u8], signature_b64: &str) -> Result<()> {
        if signature_b64.is_empty() {
            anyhow::bail!("Empty WASM signature");
        }
        let config_dir = dirs::home_dir().unwrap_or_default().join(".kairo-phantom");
        let vault = crate::identity::SignatureVault::new(&config_dir);
        let trusted_keys = vault.load_trusted_keys();
        if !trusted_keys.is_empty() {
            if vault.verify_signature(wasm_bytes, signature_b64) {
                tracing::info!("✅ WASM signature verified against trusted enterprise key vault.");
            } else {
                anyhow::bail!(
                    "WASM signature verification failed: not signed by any trusted enterprise key."
                );
            }
        } else {
            tracing::warn!("⚠️  No trusted keys registered in SignatureVault — skipping strict signature verification.");
        }
        Ok(())
    }
}

/// CLI handler: `kairo skill <sub> [args]`
pub async fn run_skill_command(sub: &str, args: &[String]) -> anyhow::Result<()> {
    let mgr = WazaSkillManager::new();
    match sub {
        "add" => {
            let url = args.first().ok_or_else(|| {
                anyhow::anyhow!("Usage: kairo skill add <url> [--allow-unsigned]")
            })?;
            let allow_unsigned = args.contains(&"--allow-unsigned".to_string());
            mgr.add_skill(url, allow_unsigned).await?;
        }
        "remove" | "rm" => {
            let id = args
                .first()
                .ok_or_else(|| anyhow::anyhow!("Usage: kairo skill remove <id>"))?;
            mgr.remove_skill(id)?;
        }
        "new" => {
            let name = args.first().map(|s| s.as_str()).unwrap_or("my-skill");
            WazaSkillManager::scaffold_skill(name)?;
        }
        "list" | "ls" => {
            let installed = mgr.list_installed();
            if installed.is_empty() {
                println!("No skills installed. Use: kairo skill add <url>");
            } else {
                println!("Installed skills ({}):", installed.len());
                for s in &installed {
                    println!(
                        "  • {} v{} [{}] — {}",
                        s.name, s.version, s.category, s.description
                    );
                }
            }
        }
        _ => {
            println!("Usage: kairo skill <add|remove|list|new> [args]");
        }
    }
    Ok(())
}
