use std::fs::File;
use std::io::Write;
use tempfile::tempdir;

#[test]
fn test_python_context_extraction_and_injection() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("test_script.py");

    let python_code = r#"import sys
import os

class MathHelper:
    def __init__(self, multiplier):
        self.multiplier = multiplier

    def process_data(self, value):
        # refactor: optimize math calculation here
        result = value * self.multiplier
        return result

    def unused_func(self):
        pass
"#;

    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(python_code.as_bytes()).unwrap();
    }

    let file_path_str = file_path.to_string_lossy().to_string();

    // The "# refactor: optimize math" prompt is on line 9 (1-indexed). Let's extract context.
    let ctx_result = phantom_core::code_context::extract_code_context(&file_path_str, 9);
    assert!(ctx_result.is_ok(), "Failed to extract code context");
    let ctx = ctx_result.unwrap();

    assert_eq!(ctx.language, "python");
    assert_eq!(ctx.enclosing_class.as_deref(), Some("MathHelper"));
    assert_eq!(
        ctx.enclosing_function.as_ref().map(|f| f.name.as_str()),
        Some("process_data")
    );

    // Check that we identified the imports
    assert!(ctx.imports.contains(&"import sys".to_string()));
    assert!(ctx.imports.contains(&"import os".to_string()));

    // Indentation checking
    assert_eq!(ctx.indentation, "        ");
    assert_eq!(ctx.cursor_col, 8);

    // Now test atomic injection
    let generated_code = r#"# Optimized implementation
        squared = value * value
        result = squared * self.multiplier"#;

    let inject_result = phantom_core::code_injector::inject_code(
        &file_path_str,
        9,
        generated_code,
        &ctx.indentation,
        ctx.line_ending,
    );
    assert!(inject_result.is_ok(), "Failed to inject code");

    let injected_content = std::fs::read_to_string(&file_path).unwrap();

    // Verify that the comment prompt `# refactor:` was removed, and the new code is there and properly indented
    assert!(injected_content.contains("        # Optimized implementation"));
    assert!(injected_content.contains("        squared = value * value"));
    assert!(injected_content.contains("        result = squared * self.multiplier"));

    // Verify that other parts of the script are intact
    assert!(injected_content.contains("class MathHelper:"));
    assert!(injected_content.contains("    def unused_func(self):"));
}

#[test]
fn test_rust_context_extraction_and_injection() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("main.rs");

    let rust_code = r#"use std::collections::HashMap;

struct Database {
    conn: String,
}

impl Database {
    fn query(&self, sql: &str) -> Result<(), String> {
        // refactor: add error handling and logs
        println!("Executing query");
        Ok(())
    }
}
"#;

    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(rust_code.as_bytes()).unwrap();
    }

    let file_path_str = file_path.to_string_lossy().to_string();

    // The "// refactor: add error" prompt is on line 9 (1-indexed). Let's extract context.
    let ctx_result = phantom_core::code_context::extract_code_context(&file_path_str, 9);
    assert!(ctx_result.is_ok(), "Failed to extract Rust code context");
    let ctx = ctx_result.unwrap();

    assert_eq!(ctx.language, "rust");
    assert_eq!(ctx.enclosing_class.as_deref(), Some("Database"));
    assert_eq!(
        ctx.enclosing_function.as_ref().map(|f| f.name.as_str()),
        Some("query")
    );

    assert!(ctx
        .imports
        .contains(&"use std::collections::HashMap;".to_string()));
    assert_eq!(ctx.indentation, "        ");

    // Inject Rust code
    let generated_code = r#"if sql.is_empty() {
            return Err("Empty query".into());
        }
        info!("SQL: {}", sql);"#;

    let inject_result = phantom_core::code_injector::inject_code(
        &file_path_str,
        9,
        generated_code,
        &ctx.indentation,
        ctx.line_ending,
    );
    assert!(inject_result.is_ok(), "Failed to inject Rust code");

    let injected_content = std::fs::read_to_string(&file_path).unwrap();

    assert!(injected_content.contains("        if sql.is_empty() {"));
    assert!(injected_content.contains("            return Err(\"Empty query\".into());"));
    assert!(injected_content.contains("        info!(\"SQL: {}\", sql);"));
    assert!(injected_content.contains("struct Database {"));
}
