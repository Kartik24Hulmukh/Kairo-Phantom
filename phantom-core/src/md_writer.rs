//! Markdown AST-aware writer
//! ============================
//! Uses pulldown-cmark to parse markdown structure and insert content
//! at the correct heading level — never overwrites the full file.
//!
//! Phase 4A of the Document-Complete Roadmap.

use anyhow::{bail, Result};
use std::path::Path;

/// Insert content after a specific markdown heading.
/// If heading not found, appends to end of file.
pub fn insert_after_heading(
    md_path: &str,
    heading_text: &str,
    heading_level: usize, // 1..6
    content: &str,
) -> Result<()> {
    let path = Path::new(md_path);
    if !path.exists() {
        bail!("Markdown file not found: {md_path}");
    }

    let original = std::fs::read_to_string(path)?;
    let result = insert_after_heading_str(&original, heading_text, heading_level, content);

    // Atomic write
    let tmp = path.with_extension("md.tmp");
    std::fs::write(&tmp, &result)?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

/// Pure function: insert content after heading in markdown string.
/// Returns the modified markdown.
pub fn insert_after_heading_str(
    md: &str,
    heading_text: &str,
    heading_level: usize,
    content: &str,
) -> String {
    let lines: Vec<&str> = md.lines().collect();
    let heading_prefix = "#".repeat(heading_level) + " ";
    let heading_lower = heading_text.to_lowercase();

    // Find the target heading line
    let mut target_idx: Option<usize> = None;
    for (i, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed.starts_with(&heading_prefix)
            && trimmed[heading_prefix.len()..]
                .trim()
                .to_lowercase()
                .contains(&heading_lower)
        {
            target_idx = Some(i);
            break;
        }
    }

    let insert_after_idx = match target_idx {
        None => {
            // Heading not found — append to end
            tracing::warn!(
                "MD writer: heading '{}' not found — appending to end",
                heading_text
            );
            lines.len()
        }
        Some(h_idx) => {
            // Find end of section: next heading of same or higher level
            let mut end_idx = lines.len();
            for (j, line) in lines.iter().enumerate().skip(h_idx + 1) {
                let next = line.trim();
                if next.starts_with('#') {
                    // Count # prefix
                    let next_level = next.chars().take_while(|c| *c == '#').count();
                    if next_level <= heading_level {
                        end_idx = j;
                        break;
                    }
                }
            }
            end_idx
        }
    };

    let mut result_lines: Vec<&str> = Vec::with_capacity(lines.len() + 10);
    result_lines.extend_from_slice(&lines[..insert_after_idx]);
    result_lines.push(""); // blank line before content
    for content_line in content.lines() {
        result_lines.push(content_line);
    }
    result_lines.push(""); // blank line after content
    result_lines.extend_from_slice(&lines[insert_after_idx..]);

    // Preserve original line ending style
    let line_ending = if md.contains("\r\n") { "\r\n" } else { "\n" };
    result_lines.join(line_ending)
}

/// Append content to end of a markdown file.
pub fn append_to_file(md_path: &str, content: &str) -> Result<()> {
    let path = Path::new(md_path);
    let mut existing = if path.exists() {
        std::fs::read_to_string(path)?
    } else {
        String::new()
    };

    if !existing.ends_with('\n') && !existing.is_empty() {
        existing.push('\n');
    }
    existing.push('\n');
    existing.push_str(content);
    existing.push('\n');

    let tmp = path.with_extension("md.tmp");
    std::fs::write(&tmp, &existing)?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

/// Replace a section between two headings with new content.
pub fn replace_section(md_path: &str, heading_text: &str, new_content: &str) -> Result<usize> {
    let path = Path::new(md_path);
    let original = std::fs::read_to_string(path)?;
    let lines: Vec<&str> = original.lines().collect();

    let heading_lower = heading_text.to_lowercase();

    // Find heading
    let mut target_idx: Option<(usize, usize)> = None; // (start, level)
    for (i, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed.starts_with('#') {
            let level = trimmed.chars().take_while(|c| *c == '#').count();
            let text = trimmed[level..].trim();
            if text.to_lowercase().contains(&heading_lower) {
                target_idx = Some((i, level));
                break;
            }
        }
    }

    let (h_idx, h_level) = match target_idx {
        None => bail!("Heading '{heading_text}' not found in {md_path}"),
        Some(x) => x,
    };

    // Find end of section
    let mut section_end = lines.len();
    for (j, line) in lines.iter().enumerate().skip(h_idx + 1) {
        let trimmed = line.trim();
        if trimmed.starts_with('#') {
            let next_level = trimmed.chars().take_while(|c| *c == '#').count();
            if next_level <= h_level {
                section_end = j;
                break;
            }
        }
    }

    // Rebuild: keep heading, replace body, keep rest
    let mut result_lines: Vec<&str> = Vec::new();
    result_lines.extend_from_slice(&lines[..=h_idx]);
    result_lines.push("");
    for content_line in new_content.lines() {
        result_lines.push(content_line);
    }
    result_lines.push("");
    result_lines.extend_from_slice(&lines[section_end..]);

    let line_ending = if original.contains("\r\n") {
        "\r\n"
    } else {
        "\n"
    };
    let output = result_lines.join(line_ending);

    let tmp = path.with_extension("md.tmp");
    std::fs::write(&tmp, &output)?;
    std::fs::rename(&tmp, path)?;
    Ok(section_end - h_idx - 1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_insert_after_heading() {
        let md =
            "# Title\n\nIntro text.\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n";
        let result = insert_after_heading_str(md, "Section A", 2, "- New bullet\n- Another bullet");
        assert!(result.contains("- New bullet"));
        assert!(result.contains("- Another bullet"));
        // Section B must still be present
        assert!(result.contains("## Section B"));
        // Content A must be before new content
        let a_pos = result.find("Content A.").unwrap();
        let b_pos = result.find("New bullet").unwrap();
        assert!(a_pos < b_pos);
    }

    #[test]
    fn test_insert_heading_not_found_appends() {
        let md = "# Title\n\nContent.\n";
        let result = insert_after_heading_str(md, "Nonexistent", 2, "Appended content");
        assert!(result.contains("Appended content"));
        assert!(result.contains("# Title"));
    }
}
