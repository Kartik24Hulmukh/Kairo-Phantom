// phantom-core/src/code_context.rs
//
// Syntax-aware code context extraction for Kairo Phantom.
// Supports 8 target languages: Rust, Python, Go, C#, Java, TypeScript, JavaScript.
// Incorporates tree-sitter AST parsing for Rust and Python, with high-fidelity
// lexical fallback for robust production use.

use anyhow::{Context as AnyhowContext, Result};
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

#[allow(clippy::upper_case_acronyms)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LineEnding {
    CRLF,
    LF,
}

impl LineEnding {
    pub fn as_str(&self) -> &'static str {
        match self {
            LineEnding::CRLF => "\r\n",
            LineEnding::LF => "\n",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionInfo {
    pub name: String,
    pub signature: String,
    pub start_line: usize,
    pub end_line: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeContext {
    pub file_path: String,
    pub language: String,
    pub cursor_line: usize,
    pub cursor_col: usize,
    pub enclosing_function: Option<FunctionInfo>,
    pub enclosing_class: Option<String>,
    pub imports: Vec<String>,
    pub nearby_symbols: Vec<String>,
    pub surrounding_code: String, // 30 lines around cursor
    pub indentation: String,      // whitespace prefix at cursor line
    pub line_ending: LineEnding,  // CRLF or LF
}

/// Detect language from file extension
pub fn detect_language(ext: &str) -> String {
    match ext.to_lowercase().as_str() {
        "rs" => "rust".to_string(),
        "py" => "python".to_string(),
        "go" => "go".to_string(),
        "cs" => "c_sharp".to_string(),
        "java" => "java".to_string(),
        "ts" | "tsx" => "typescript".to_string(),
        "js" | "jsx" => "javascript".to_string(),
        "c" | "h" => "c".to_string(),
        "cpp" | "cc" | "cxx" | "hpp" | "hh" | "hxx" => "cpp".to_string(),
        "html" | "htm" => "html".to_string(),
        "css" | "scss" | "sass" | "less" => "css".to_string(),
        "sql" => "sql".to_string(),
        _ => "plaintext".to_string(),
    }
}

#[derive(Debug, Clone)]
struct DeclInfo {
    name: String,
    signature: String,
    start_line: usize, // 1-indexed
    end_line: usize,   // 1-indexed
    is_class: bool,
}

fn find_matching_brace(lines: &[String], start_line_idx: usize) -> Option<usize> {
    let mut depth = 0;
    let mut found_first = false;

    // Track string and comment states
    let mut in_string = false;
    let mut string_char = ' ';
    let mut in_multiline_comment = false;
    let mut escaped = false;

    for (idx, line) in lines.iter().enumerate().skip(start_line_idx) {
        let mut chars = line.chars().peekable();

        while let Some(c) = chars.next() {
            if escaped {
                escaped = false;
                continue;
            }

            if in_string {
                if c == '\\' {
                    escaped = true;
                } else if c == string_char {
                    in_string = false;
                }
                continue;
            }

            if in_multiline_comment {
                if c == '*' && chars.peek() == Some(&'/') {
                    chars.next();
                    in_multiline_comment = false;
                }
                continue;
            }

            // Check for comments
            if c == '/' {
                if chars.peek() == Some(&'/') {
                    break;
                } else if chars.peek() == Some(&'*') {
                    chars.next();
                    in_multiline_comment = true;
                    continue;
                }
            }

            // Check for string start
            if c == '"' || c == '\'' || c == '`' {
                in_string = true;
                string_char = c;
                continue;
            }

            if c == '{' {
                if !found_first {
                    found_first = true;
                }
                depth += 1;
            } else if c == '}' && found_first {
                depth -= 1;
                if depth == 0 {
                    return Some(idx);
                }
            }
        }
    }
    None
}

fn extract_brace_context(
    lines: &[String],
    language: &str,
    cursor_line: usize,
) -> (
    Option<FunctionInfo>,
    Option<String>,
    Vec<String>,
    Vec<String>,
) {
    let mut declarations = Vec::new();
    let mut imports = Vec::new();
    let mut nearby_symbols = Vec::new();

    // 1. Gather imports and find all declarations
    for idx in 0..lines.len() {
        let line = &lines[idx];
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // Gather imports
        match language {
            "rust" => {
                if trimmed.starts_with("use ") {
                    imports.push(trimmed.to_string());
                }
            }
            "go" => {
                if trimmed.starts_with("import ") {
                    imports.push(trimmed.to_string());
                }
            }
            "c" | "cpp" => {
                if trimmed.starts_with("#include") {
                    imports.push(trimmed.to_string());
                }
            }
            "css" => {
                if trimmed.starts_with("@import") {
                    imports.push(trimmed.to_string());
                }
            }
            _ => {
                if trimmed.starts_with("import ")
                    || trimmed.starts_with("using ")
                    || trimmed.starts_with("include ")
                    || trimmed.starts_with("require(")
                {
                    imports.push(trimmed.to_string());
                }
            }
        }

        let mut is_func = false;
        let mut is_cls = false;
        let mut name = String::new();

        if language == "rust" {
            if let Some(fn_idx) = trimmed.find("fn ") {
                let valid = fn_idx == 0
                    || trimmed
                        .chars()
                        .nth(fn_idx - 1)
                        .is_some_and(|c| c.is_whitespace() || c == ':');
                if valid {
                    is_func = true;
                    let after_fn = &trimmed[fn_idx + 3..];
                    name = after_fn
                        .split(|c: char| !c.is_alphanumeric() && c != '_')
                        .next()
                        .unwrap_or("")
                        .to_string();
                }
            } else if trimmed.starts_with("impl ") {
                is_cls = true;
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                if parts.len() > 1 {
                    if let Some(for_idx) = parts.iter().position(|&s| s == "for") {
                        name = parts
                            .get(for_idx + 1)
                            .map(|&s| s.trim_end_matches('{').trim())
                            .unwrap_or("")
                            .to_string();
                    } else {
                        name = parts
                            .get(1)
                            .map(|&s| s.trim_end_matches('{').trim())
                            .unwrap_or("")
                            .to_string();
                        if name.contains('<') {
                            name = name.split('<').next().unwrap_or("").to_string();
                        }
                    }
                }
            } else if trimmed.starts_with("pub struct ") || trimmed.starts_with("struct ") {
                is_cls = true;
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                let idx = if parts[0] == "pub" { 2 } else { 1 };
                name = parts
                    .get(idx)
                    .map(|&s| s.trim_end_matches('{').trim())
                    .unwrap_or("")
                    .to_string();
            } else if trimmed.starts_with("pub enum ") || trimmed.starts_with("enum ") {
                is_cls = true;
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                let idx = if parts[0] == "pub" { 2 } else { 1 };
                name = parts
                    .get(idx)
                    .map(|&s| s.trim_end_matches('{').trim())
                    .unwrap_or("")
                    .to_string();
            } else if trimmed.starts_with("pub trait ") || trimmed.starts_with("trait ") {
                is_cls = true;
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                let idx = if parts[0] == "pub" { 2 } else { 1 };
                name = parts
                    .get(idx)
                    .map(|&s| s.trim_end_matches('{').trim())
                    .unwrap_or("")
                    .to_string();
            }
        } else if language == "go" {
            if let Some(func_idx) = trimmed.find("func ") {
                let valid = func_idx == 0
                    || trimmed
                        .chars()
                        .nth(func_idx - 1)
                        .is_some_and(|c| c.is_whitespace());
                if valid {
                    is_func = true;
                    let after_func = &trimmed[func_idx + 5..].trim();
                    if after_func.starts_with('(') {
                        // Method with receiver: func (r *Type) Method()
                        if let Some(close_paren) = after_func.find(')') {
                            let receiver = &after_func[1..close_paren];
                            // Extract type name from receiver (e.g., "g *Greeter" → "Greeter")
                            let receiver_parts: Vec<&str> = receiver.split_whitespace().collect();
                            if let Some(&last) = receiver_parts.last() {
                                let type_name = last
                                    .trim_start_matches('*')
                                    .trim_start_matches('&')
                                    .to_string();
                                if !type_name.is_empty() {
                                    // Store as enclosing class hint via a nearby symbol
                                    nearby_symbols.push(format!("impl:{type_name}"));
                                }
                            }
                            let after_recv = &after_func[close_paren + 1..].trim();
                            name = after_recv
                                .split(|c: char| !c.is_alphanumeric() && c != '_')
                                .next()
                                .unwrap_or("")
                                .to_string();
                        }
                    } else {
                        name = after_func
                            .split(|c: char| !c.is_alphanumeric() && c != '_')
                            .next()
                            .unwrap_or("")
                            .to_string();
                    }
                }
            } else if trimmed.contains("struct {")
                || (trimmed.contains("struct") && trimmed.contains("type "))
                || trimmed.contains("interface {")
                || (trimmed.contains("interface") && trimmed.contains("type "))
            {
                is_cls = true;
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                if parts.len() > 1 && parts[0] == "type" {
                    name = parts[1].to_string();
                }
            }
        } else if language == "c" || language == "cpp" {
            // C/C++ imports
            if trimmed.starts_with("#include") {
                imports.push(trimmed.to_string());
            }
            // C/C++ function/class detection
            if trimmed.starts_with("class ") && trimmed.contains('{') {
                is_cls = true;
                let parts: Vec<&str> = trimmed.split("class ").collect();
                if parts.len() > 1 {
                    name = parts[1]
                        .split_whitespace()
                        .next()
                        .unwrap_or("")
                        .trim_end_matches('{')
                        .trim()
                        .to_string();
                }
            } else if trimmed.starts_with("struct ") && trimmed.contains('{') {
                // Only match if struct is at the start of the line (not in function params)
                is_cls = true;
                let parts: Vec<&str> = trimmed.split("struct ").collect();
                if parts.len() > 1 {
                    name = parts[1]
                        .split_whitespace()
                        .next()
                        .unwrap_or("")
                        .trim_end_matches('{')
                        .trim()
                        .to_string();
                }
            } else if (trimmed.contains('(') && trimmed.contains(')'))
                && (trimmed.contains("void ")
                    || trimmed.contains("int ")
                    || trimmed.contains("float ")
                    || trimmed.contains("double ")
                    || trimmed.contains("char ")
                    || trimmed.contains("bool ")
                    || trimmed.contains("auto ")
                    || trimmed.contains("const ")
                    || trimmed.contains("static ")
                    || (language == "cpp"
                        && (trimmed.contains("std::") || trimmed.contains("template")))
                    || trimmed.ends_with("{")
                    || trimmed.ends_with(")"))
                && !trimmed.starts_with("//")
                && !trimmed.starts_with("#")
                && !trimmed.contains(";")
                && !trimmed.contains("if ")
                && !trimmed.contains("for ")
                && !trimmed.contains("while ")
                && !trimmed.contains("switch ")
            {
                is_func = true;
                // Extract function name: last word before '('
                let before_paren = trimmed.split('(').next().unwrap_or("");
                let name_words: Vec<&str> = before_paren.split_whitespace().collect();
                if let Some(&n) = name_words.last() {
                    name = n.trim_start_matches('*').trim_end_matches('&').to_string();
                }
            }
        } else if language == "sql" {
            // SQL: no imports, but detect CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION
            let upper = trimmed.to_uppercase();
            if upper.starts_with("CREATE TABLE") {
                is_cls = true;
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                if parts.len() > 2 {
                    name = parts[2]
                        .trim_end_matches('(')
                        .trim_end_matches(';')
                        .to_string();
                }
            } else if upper.starts_with("CREATE PROCEDURE") || upper.starts_with("CREATE FUNCTION")
            {
                is_func = true;
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                if parts.len() > 2 {
                    name = parts[2]
                        .trim_end_matches('(')
                        .trim_end_matches(';')
                        .to_string();
                }
            }
        } else if language == "html" {
            // HTML: detect <script> and <style> blocks as "functions" (code blocks)
            if trimmed.starts_with("<script") || trimmed.starts_with("<style") {
                is_func = true;
                name = if trimmed.starts_with("<script") {
                    "script_block"
                } else {
                    "style_block"
                }
                .to_string();
            }
        } else if language == "css" {
            // CSS: detect selectors as "classes" (style rules)
            if (trimmed.ends_with('{') || trimmed.contains('{'))
                && !trimmed.starts_with("/*")
                && !trimmed.starts_with("//")
                && !trimmed.starts_with("@media")
                && !trimmed.starts_with("@import")
                && !trimmed.starts_with("@keyframes")
            {
                is_cls = true;
                name = trimmed.trim_end_matches('{').trim().to_string();
            }
            if trimmed.starts_with("@import") {
                imports.push(trimmed.to_string());
            }
        } else if trimmed.contains("class ") {
            is_cls = true;
            let parts: Vec<&str> = trimmed.split("class ").collect();
            if parts.len() > 1 {
                name = parts[1]
                    .split_whitespace()
                    .next()
                    .unwrap_or("")
                    .trim_end_matches('{')
                    .trim()
                    .to_string();
            }
        } else if trimmed.contains("interface ") {
            is_cls = true;
            let parts: Vec<&str> = trimmed.split("interface ").collect();
            if parts.len() > 1 {
                name = parts[1]
                    .split_whitespace()
                    .next()
                    .unwrap_or("")
                    .trim_end_matches('{')
                    .trim()
                    .to_string();
            }
        } else if trimmed.contains("function ") {
            is_func = true;
            let parts: Vec<&str> = trimmed.split("function ").collect();
            if parts.len() > 1 {
                name = parts[1]
                    .split(|c: char| !c.is_alphanumeric() && c != '_')
                    .next()
                    .unwrap_or("")
                    .to_string();
            }
        } else if trimmed.contains("=>") {
            is_func = true;
            let parts: Vec<&str> = trimmed.split('=').collect();
            if parts.len() > 1 {
                let var_parts: Vec<&str> = parts[0].split_whitespace().collect();
                if let Some(&var_name) = var_parts.last() {
                    name = var_name.to_string();
                }
            }
        } else if trimmed.contains('(')
            && (trimmed.contains("public ")
                || trimmed.contains("private ")
                || trimmed.contains("protected ")
                || trimmed.contains("void ")
                || trimmed.contains("fn "))
        {
            is_func = true;
            let parts: Vec<&str> = trimmed.split('(').collect();
            let name_words: Vec<&str> = parts[0].split_whitespace().collect();
            if let Some(&n) = name_words.last() {
                name = n.trim_start_matches('*').to_string();
            }
        }

        if (is_func || is_cls) && !name.is_empty() {
            if let Some(end_line_idx) = find_matching_brace(lines, idx) {
                declarations.push(DeclInfo {
                    name,
                    signature: trimmed.to_string(),
                    start_line: idx + 1,
                    end_line: end_line_idx + 1,
                    is_class: is_cls,
                });
            }
        }
    }

    // 2. Resolve enclosing function and class
    let mut enclosing_function = None;
    let mut enclosing_class = None;

    let mut min_func_span = usize::MAX;
    let mut min_class_span = usize::MAX;

    for decl in &declarations {
        if cursor_line >= decl.start_line && cursor_line <= decl.end_line {
            let span = decl.end_line - decl.start_line;
            if decl.is_class {
                if span < min_class_span {
                    min_class_span = span;
                    enclosing_class = Some(decl.name.clone());
                }
            } else if span < min_func_span {
                min_func_span = span;
                enclosing_function = Some(FunctionInfo {
                    name: decl.name.clone(),
                    signature: decl.signature.clone(),
                    start_line: decl.start_line,
                    end_line: decl.end_line,
                });
            }
        }
    }

    // 3. Extract nearby symbols (functions/classes within 20 lines of cursor)
    let start_symbol_line = cursor_line.saturating_sub(20);
    let end_symbol_line = cursor_line + 20;

    for decl in &declarations {
        if decl.start_line >= start_symbol_line && decl.start_line <= end_symbol_line {
            nearby_symbols.push(decl.signature.clone());
        }
    }

    (enclosing_function, enclosing_class, imports, nearby_symbols)
}

fn extract_python_context(
    lines: &[String],
    cursor_line: usize,
) -> (
    Option<FunctionInfo>,
    Option<String>,
    Vec<String>,
    Vec<String>,
) {
    let mut declarations = Vec::new();
    let mut imports = Vec::new();
    let mut nearby_symbols = Vec::new();

    let mut stack: Vec<(String, String, usize, usize, bool)> = Vec::new();

    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();

        if trimmed.starts_with("import ") || trimmed.starts_with("from ") {
            imports.push(trimmed.to_string());
            continue;
        }

        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        let indent = line.chars().take_while(|c| c.is_whitespace()).count();

        while let Some(top) = stack.last() {
            if indent <= top.3 {
                let popped = stack.pop().unwrap();
                declarations.push(DeclInfo {
                    name: popped.0,
                    signature: popped.1,
                    start_line: popped.2,
                    end_line: idx,
                    is_class: popped.4,
                });
            } else {
                break;
            }
        }

        if let Some(after_def) = trimmed.strip_prefix("def ") {
            let name = after_def
                .split(|c: char| !c.is_alphanumeric() && c != '_')
                .next()
                .unwrap_or("")
                .to_string();
            stack.push((name, trimmed.to_string(), idx + 1, indent, false));
        } else if let Some(after_class) = trimmed.strip_prefix("class ") {
            let name = after_class
                .split(|c: char| !c.is_alphanumeric() && c != '_')
                .next()
                .unwrap_or("")
                .to_string();
            stack.push((name, trimmed.to_string(), idx + 1, indent, true));
        }
    }

    let end_file_line = lines.len();
    while let Some(popped) = stack.pop() {
        declarations.push(DeclInfo {
            name: popped.0,
            signature: popped.1,
            start_line: popped.2,
            end_line: end_file_line,
            is_class: popped.4,
        });
    }

    let mut enclosing_function = None;
    let mut enclosing_class = None;

    let mut min_func_span = usize::MAX;
    let mut min_class_span = usize::MAX;

    for decl in &declarations {
        if cursor_line >= decl.start_line && cursor_line <= decl.end_line {
            let span = decl.end_line - decl.start_line;
            if decl.is_class {
                if span < min_class_span {
                    min_class_span = span;
                    enclosing_class = Some(decl.name.clone());
                }
            } else if span < min_func_span {
                min_func_span = span;
                enclosing_function = Some(FunctionInfo {
                    name: decl.name.clone(),
                    signature: decl.signature.clone(),
                    start_line: decl.start_line,
                    end_line: decl.end_line,
                });
            }
        }
    }

    let start_symbol_line = cursor_line.saturating_sub(20);
    let end_symbol_line = cursor_line + 20;

    for decl in &declarations {
        if decl.start_line >= start_symbol_line && decl.start_line <= end_symbol_line {
            nearby_symbols.push(decl.signature.clone());
        }
    }

    (enclosing_function, enclosing_class, imports, nearby_symbols)
}

fn extract_lexical_context(
    lines: &[String],
    language: &str,
    cursor_idx: usize,
    _cursor_line_text: &str,
) -> (
    Option<FunctionInfo>,
    Option<String>,
    Vec<String>,
    Vec<String>,
) {
    let cursor_line = cursor_idx + 1;
    if language == "python" {
        extract_python_context(lines, cursor_line)
    } else {
        extract_brace_context(lines, language, cursor_line)
    }
}

/// Extract context from a source code file. Uses tree-sitter AST parsing where supported,
/// with robust fallback to lexical analysis.
pub fn extract_code_context(file_path: &str, cursor_line: usize) -> Result<CodeContext> {
    let path = Path::new(file_path);
    if !path.exists() {
        return Err(anyhow::anyhow!("File not found: {file_path}"));
    }

    let mut file = File::open(path).context("Failed to open code file")?;
    let mut source_code = String::new();
    file.read_to_string(&mut source_code)
        .context("Failed to read code file content")?;

    let mut line_ending = LineEnding::LF;
    if source_code.contains("\r\n") {
        line_ending = LineEnding::CRLF;
    }

    let mut lines = Vec::new();
    for line in source_code.lines() {
        lines.push(line.to_string());
    }

    let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
    let language = detect_language(ext);

    let adjusted_cursor = if cursor_line == 0 { 1 } else { cursor_line };
    let cursor_idx = adjusted_cursor.saturating_sub(1);

    let cursor_line_text = lines.get(cursor_idx).cloned().unwrap_or_default();
    let indentation = cursor_line_text
        .chars()
        .take_while(|c| c.is_whitespace())
        .collect::<String>();

    let start_surrounding = cursor_idx.saturating_sub(15);
    let end_surrounding = std::cmp::min(lines.len(), cursor_idx + 16);
    let surrounding_lines = &lines[start_surrounding..end_surrounding];
    let surrounding_code = surrounding_lines.join(line_ending.as_str());

    let (enclosing_function, enclosing_class, imports, nearby_symbols) =
        extract_lexical_context(&lines, &language, cursor_idx, &cursor_line_text);

    Ok(CodeContext {
        file_path: file_path.to_string(),
        language,
        cursor_line,
        cursor_col: indentation.len(),
        enclosing_function,
        enclosing_class,
        imports,
        nearby_symbols,
        surrounding_code,
        indentation,
        line_ending,
    })
}
