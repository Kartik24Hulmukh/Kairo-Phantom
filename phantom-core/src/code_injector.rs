// phantom-core/src/code_injector.rs
//
// Atomically injects generated code into source files, preserving indentation,
// line endings, and ensuring safety through backup/temp-file writes.

use crate::code_context::LineEnding;
use anyhow::{Context, Result};
use std::fs::{self, File};
use std::io::Write;
use std::path::Path;

/// Injects generated code at the target cursor line of a file.
/// Prepend `indentation` to each line of the generated code.
/// Preserves the original `line_ending`.
/// Saves the file atomically via a temporary file in the same directory, then renames.
pub fn inject_code(
    file_path: &str,
    target_line: usize,
    generated_code: &str,
    indentation: &str,
    line_ending: LineEnding,
) -> Result<()> {
    let path = Path::new(file_path);
    if !path.exists() {
        return Err(anyhow::anyhow!("File does not exist: {file_path}"));
    }

    // Read the entire file lines
    let content = fs::read_to_string(path).context("Failed to read original code file")?;
    let lines: Vec<String> = content.lines().map(|s| s.to_string()).collect();

    // Format the generated code lines with the cursor's indentation.
    // However, if a line in the generated code is empty, we do not add trailing whitespace.
    let ending_str = line_ending.as_str();
    let formatted_generated: Vec<String> = generated_code
        .lines()
        .map(|line| {
            if line.trim().is_empty() {
                String::new()
            } else {
                format!("{indentation}{line}")
            }
        })
        .collect();

    // Identify target index. If target_line is out of bounds, append to end.
    let target_idx = target_line.saturating_sub(1);

    // Inject the formatted lines.
    // Replace the line at target_idx (the command prompt) with the generated code.
    let mut new_lines = Vec::new();
    for (i, line) in lines.iter().enumerate() {
        if i == target_idx {
            for gen_line in &formatted_generated {
                new_lines.push(gen_line.clone());
            }
        } else {
            new_lines.push(line.clone());
        }
    }

    // If target_line was beyond file length, we append it.
    if target_idx >= lines.len() {
        for gen_line in &formatted_generated {
            new_lines.push(gen_line.clone());
        }
    }

    // Reconstruct the file content with the correct line ending.
    let mut output = new_lines.join(ending_str);
    // Ensure trailing newline if original had one
    if content.ends_with('\n') {
        output.push_str(ending_str);
    }

    // Write to a temporary file in the same directory to guarantee atomic rename
    let dir = path.parent().unwrap_or_else(|| Path::new("."));
    let temp_path = dir.join(format!(".kairo_tmp_{}.tmp", uuid::Uuid::new_v4()));

    {
        let mut temp_file =
            File::create(&temp_path).context("Failed to create temporary file for atomic write")?;
        temp_file
            .write_all(output.as_bytes())
            .context("Failed to write to temporary file")?;
        temp_file
            .sync_all()
            .context("Failed to sync temporary file to disk")?;
    }

    // Rename temp file to target path (atomic rename)
    fs::rename(&temp_path, path).context("Failed to replace file atomically")?;

    // Cleanup temp file just in case rename failed and left it behind
    if temp_path.exists() {
        let _ = fs::remove_file(temp_path);
    }

    Ok(())
}
