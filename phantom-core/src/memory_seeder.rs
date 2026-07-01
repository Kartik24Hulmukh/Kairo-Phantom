//! Memory Seeder — P1-A2
//! `kairo seed <folder>` — Scans existing documents to pre-populate MemMachine.
//! Solves the cold-start problem by extracting style patterns from a folder of docs.

use crate::memory::MemMachine;
use anyhow::Result;
use std::path::{Path, PathBuf};

pub struct MemorySeeder;

impl MemorySeeder {
    /// Seed MemMachine from all documents in a folder. Returns count of seeded docs.
    pub async fn seed_from_folder(folder: &Path, mem: &MemMachine) -> Result<usize> {
        let supported_exts = [
            "docx", "doc", "pptx", "ppt", "xlsx", "xls", "txt", "md", "pdf",
        ];
        let mut seeded = 0;

        let entries = walkdir_simple(folder);
        for path in entries {
            let ext = path
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();

            if !supported_exts.contains(&ext.as_str()) {
                continue;
            }

            // Read text (best-effort — skip unreadable files)
            let text = match std::fs::read_to_string(&path) {
                Ok(t) if !t.trim().is_empty() => t,
                _ => continue,
            };

            let style = extract_style_signals(&text);
            let app_ctx = path
                .extension()
                .unwrap_or_default()
                .to_string_lossy()
                .to_uppercase()
                .to_string();

            // Store inferred preferences as MemMachine episodes
            for (pref_key, pref_val) in &style {
                let content =
                    format!("Style preference from existing docs: {pref_key} = {pref_val}");
                let _ = mem
                    .remember(
                        &content,
                        Some(&text[..text.len().min(500)]),
                        &app_ctx,
                        Some(pref_key.as_str()),
                        true, // is_ground_truth — seeded from real user docs
                        vec!["seeded", "style-preference"],
                    )
                    .await;
            }

            seeded += 1;
            tracing::info!(
                "🌱 Seeded: {} ({} style signals)",
                path.display(),
                style.len()
            );
        }

        tracing::info!("✅ Memory seeding complete: {} documents processed", seeded);
        Ok(seeded)
    }
}

/// Extract style signals from document text.
/// Returns key-value pairs like ("format_preference", "bullet_points")
fn extract_style_signals(text: &str) -> Vec<(String, String)> {
    let mut signals = Vec::new();
    let words: Vec<&str> = text.split_whitespace().collect();
    let word_count = words.len();
    if word_count < 10 {
        return signals;
    }

    // 1. Avg sentence length → concise vs detailed
    let sentences = text
        .chars()
        .filter(|&c| c == '.' || c == '!' || c == '?')
        .count()
        .max(1);
    let avg_sentence_len = word_count / sentences;
    let length_pref = if avg_sentence_len < 12 {
        "concise"
    } else if avg_sentence_len < 20 {
        "moderate"
    } else {
        "detailed"
    };
    signals.push(("sentence_style".to_string(), length_pref.to_string()));

    // 2. Bullet ratio → format preference
    let bullet_lines = text
        .lines()
        .filter(|l| {
            let t = l.trim();
            t.starts_with("• ") || t.starts_with("- ") || t.starts_with("* ") || t.starts_with("· ")
        })
        .count();
    let total_lines = text.lines().count().max(1);
    let bullet_ratio = bullet_lines as f32 / total_lines as f32;
    signals.push((
        "format_preference".to_string(),
        if bullet_ratio > 0.25 {
            "bullet_points"
        } else {
            "prose"
        }
        .to_string(),
    ));

    // 3. Contractions → formal vs casual
    let contractions = [
        "don't", "can't", "won't", "it's", "i'm", "we're", "they're", "isn't", "aren't", "i'll",
        "you'll",
    ];
    let has_contractions = contractions.iter().any(|c| text.to_lowercase().contains(c));
    signals.push((
        "tone".to_string(),
        if has_contractions { "casual" } else { "formal" }.to_string(),
    ));

    // 4. Avg word length → vocabulary level
    let avg_word_len = words.iter().map(|w| w.len()).sum::<usize>() / word_count;
    let vocab_level = if avg_word_len < 5 {
        "simple"
    } else if avg_word_len < 7 {
        "moderate"
    } else {
        "advanced"
    };
    signals.push(("vocabulary".to_string(), vocab_level.to_string()));

    // 5. Heading count → structured vs flowing
    let heading_lines = text.lines().filter(|l| l.trim().starts_with('#')).count();
    if heading_lines > 3 {
        signals.push(("structure".to_string(), "well-structured".to_string()));
    }

    signals
}

/// Simple recursive directory walker returning file paths.
fn walkdir_simple(folder: &Path) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Ok(entries) = std::fs::read_dir(folder) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                paths.extend(walkdir_simple(&path));
            } else {
                paths.push(path);
            }
        }
    }
    paths
}

/// CLI handler: `kairo seed <folder>`
pub async fn run_seed_command(folder_str: &str) -> Result<()> {
    let folder = PathBuf::from(folder_str);
    if !folder.exists() {
        anyhow::bail!("Folder not found: {folder_str}");
    }

    println!("🌱 Kairo Memory Seeding");
    println!("   Scanning: {}", folder.display());
    println!("   This extracts style patterns to pre-populate MemMachine.\n");

    let mem_vault = dirs::home_dir().unwrap_or_default().join(".kairo-phantom");

    let mem = MemMachine::new(mem_vault)?;
    let count = MemorySeeder::seed_from_folder(&folder, &mem).await?;

    println!("✅ Done! Seeded {count} documents into MemMachine.");
    println!("   Kairo now understands your writing style from day one.");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[tokio::test]
    async fn test_seed_empty_folder() {
        let dir = tempdir().unwrap();
        let mem_dir = tempdir().unwrap();
        let mem = MemMachine::new(mem_dir.path().to_path_buf()).unwrap();
        let result = MemorySeeder::seed_from_folder(dir.path(), &mem).await;
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), 0, "Empty folder should seed 0 docs");
    }

    #[tokio::test]
    async fn test_seed_text_file() {
        let dir = tempdir().unwrap();
        // Create a markdown file with bullet points
        std::fs::write(
            dir.path().join("sample.md"),
            "# My Doc\n\n• Point one\n• Point two\n• Point three\nThis is formal prose.",
        )
        .unwrap();
        let mem_dir = tempdir().unwrap();
        let mem = MemMachine::new(mem_dir.path().to_path_buf()).unwrap();
        let result = MemorySeeder::seed_from_folder(dir.path(), &mem).await;
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), 1, "Should seed exactly 1 file");
    }

    #[test]
    fn test_style_signals_extraction() {
        let bullet_text = "• Point one\n• Point two\n• Point three\nSome prose here.";
        let signals = extract_style_signals(bullet_text);
        let format_sig = signals.iter().find(|(k, _)| k == "format_preference");
        assert!(format_sig.is_some());
        assert_eq!(format_sig.unwrap().1, "bullet_points");
    }
}
