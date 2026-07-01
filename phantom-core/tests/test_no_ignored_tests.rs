use std::fs;
use std::path::Path;

fn scan_dir(dir: &Path, errors: &mut Vec<String>) {
    if !dir.exists() {
        return;
    }
    for entry in fs::read_dir(dir).unwrap() {
        let entry = entry.unwrap();
        let path = entry.path();
        if path.is_dir() {
            scan_dir(&path, errors);
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            let content = fs::read_to_string(&path).unwrap();
            let ignore_pattern = format!("{}[ignore]", '#');
            for (line_idx, line) in content.lines().enumerate() {
                // Skip commented lines
                let trimmed = line.trim();
                if trimmed.starts_with("//") {
                    continue;
                }
                if trimmed.contains(&ignore_pattern) {
                    errors.push(format!(
                        "Found {} in {}:{}",
                        ignore_pattern,
                        path.display(),
                        line_idx + 1
                    ));
                }
            }
        }
    }
}

#[test]
fn test_no_ignored_rust_tests() {
    let mut errors = Vec::new();

    // Find phantom-core root directory
    let root = if Path::new("../phantom-core").exists() {
        Path::new("../phantom-core")
    } else if Path::new("phantom-core").exists() {
        Path::new("phantom-core")
    } else {
        Path::new(".")
    };

    scan_dir(&root.join("src"), &mut errors);
    scan_dir(&root.join("tests"), &mut errors);

    if !errors.is_empty() {
        panic!(
            "❌ Ignored Rust tests are strictly forbidden! Please remove all ignored annotations:\n{}",
            errors.join("\n")
        );
    }
}
