// phantom-core/tests/test_domain7_code.rs
//
// Domain 7: Code — Comprehensive test suite for code_context + code_injector
// Tests 10 language extraction, injection, and edge cases.

use std::fs::File;
use std::io::Write;
use tempfile::tempdir;

#[test]
fn test_detect_language_10_languages() {
    assert_eq!(phantom_core::code_context::detect_language("rs"), "rust");
    assert_eq!(phantom_core::code_context::detect_language("py"), "python");
    assert_eq!(phantom_core::code_context::detect_language("go"), "go");
    assert_eq!(phantom_core::code_context::detect_language("cs"), "c_sharp");
    assert_eq!(phantom_core::code_context::detect_language("java"), "java");
    assert_eq!(
        phantom_core::code_context::detect_language("ts"),
        "typescript"
    );
    assert_eq!(
        phantom_core::code_context::detect_language("js"),
        "javascript"
    );
    assert_eq!(phantom_core::code_context::detect_language("c"), "c");
    assert_eq!(phantom_core::code_context::detect_language("cpp"), "cpp");
    assert_eq!(phantom_core::code_context::detect_language("html"), "html");
    assert_eq!(phantom_core::code_context::detect_language("css"), "css");
    assert_eq!(phantom_core::code_context::detect_language("sql"), "sql");
    assert_eq!(
        phantom_core::code_context::detect_language("unknown"),
        "plaintext"
    );
}

#[test]
fn test_c_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("main.c");
    let c_code = r#"#include <stdio.h>
#include <stdlib.h>

struct Point {
    int x;
    int y;
};

int calculate_distance(struct Point p1, struct Point p2) {
    // refactor: use sqrt for euclidean distance
    int dx = p1.x - p2.x;
    int dy = p1.y - p2.y;
    return dx * dx + dy * dy;
}
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(c_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 11).unwrap();
    assert_eq!(ctx.language, "c");
    assert_eq!(
        ctx.enclosing_function.as_ref().map(|f| f.name.as_str()),
        Some("calculate_distance")
    );
    assert!(ctx.imports.iter().any(|i| i.contains("#include <stdio.h>")));
    assert!(ctx
        .imports
        .iter()
        .any(|i| i.contains("#include <stdlib.h>")));
}

#[test]
fn test_cpp_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("main.cpp");
    let cpp_code = r#"#include <iostream>
#include <vector>

class DataProcessor {
public:
    void process(const std::vector<int>& data) {
        // refactor: add parallel processing
        for (auto& val : data) {
            val *= 2;
        }
    }
};
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(cpp_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 8).unwrap();
    assert_eq!(ctx.language, "cpp");
    assert_eq!(ctx.enclosing_class.as_deref(), Some("DataProcessor"));
    assert_eq!(
        ctx.enclosing_function.as_ref().map(|f| f.name.as_str()),
        Some("process")
    );
    assert!(ctx
        .imports
        .iter()
        .any(|i| i.contains("#include <iostream>")));
}

#[test]
fn test_sql_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("schema.sql");
    let sql_code = r#"CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
);

CREATE FUNCTION calculate_total(user_id INTEGER)
RETURNS INTEGER AS $$
BEGIN
    -- refactor: add index for performance
    RETURN 0;
END;
$$ LANGUAGE plpgsql;
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(sql_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 10).unwrap();
    assert_eq!(ctx.language, "sql");
}

#[test]
fn test_html_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("page.html");
    let html_code = r#"<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
    <script>
        // refactor: add event listener
        console.log("hello");
    </script>
</head>
<body>
    <h1>Hello</h1>
</body>
</html>
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(html_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 7).unwrap();
    assert_eq!(ctx.language, "html");
}

#[test]
fn test_css_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("styles.css");
    let css_code = r#"@import url('https://fonts.googleapis.com/css?family=Roboto');

body {
    margin: 0;
    padding: 0;
}

.container {
    /* refactor: use flexbox */
    display: block;
    width: 100%;
}
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(css_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 11).unwrap();
    assert_eq!(ctx.language, "css");
    assert!(ctx.imports.iter().any(|i| i.contains("@import")));
}

#[test]
fn test_typescript_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("app.ts");
    let ts_code = r#"import { Component } from '@angular/core';

@Component({
    selector: 'app-root',
    template: '<h1>Hello</h1>'
})
export class AppComponent {
    title = 'Kairo';

    ngOnInit() {
        // refactor: add lifecycle hook logic
        console.log(this.title);
    }
}
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(ts_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 12).unwrap();
    assert_eq!(ctx.language, "typescript");
    assert_eq!(ctx.enclosing_class.as_deref(), Some("AppComponent"));
}

#[test]
fn test_go_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("main.go");
    let go_code = r#"package main

import "fmt"
import "strings"

type Greeter struct {
    name string
}

func (g *Greeter) SayHello() {
    // refactor: add multi-language support
    fmt.Printf("Hello, %s!\n", g.name)
}
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(go_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 12).unwrap();
    assert_eq!(ctx.language, "go");
    assert_eq!(
        ctx.enclosing_function.as_ref().map(|f| f.name.as_str()),
        Some("SayHello")
    );
    assert!(ctx.imports.iter().any(|i| i.contains("import \"fmt\"")));
    // The struct Greeter is on line 5-7, cursor is on line 12 (inside SayHello)
    // The method receiver type is stored in nearby_symbols
    assert!(ctx.nearby_symbols.iter().any(|s| s.contains("Greeter")));
}

#[test]
fn test_java_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("Main.java");
    let java_code = r#"import java.util.List;
import java.util.ArrayList;

public class Main {
    public static void main(String[] args) {
        // refactor: add input validation
        List<String> items = new ArrayList<>();
        System.out.println(items.size());
    }
}
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(java_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 7).unwrap();
    assert_eq!(ctx.language, "java");
    assert_eq!(ctx.enclosing_class.as_deref(), Some("Main"));
    assert_eq!(
        ctx.enclosing_function.as_ref().map(|f| f.name.as_str()),
        Some("main")
    );
    assert!(ctx
        .imports
        .iter()
        .any(|i| i.contains("import java.util.List;")));
}

#[test]
fn test_javascript_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("app.js");
    let js_code = r#"const express = require('express');

class App {
    constructor() {
        this.app = express();
    }

    setupRoutes() {
        // refactor: add middleware
        this.app.get('/', (req, res) => {
            res.send('Hello');
        });
    }
}
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(js_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 11).unwrap();
    assert_eq!(ctx.language, "javascript");
    assert_eq!(ctx.enclosing_class.as_deref(), Some("App"));
}

#[test]
fn test_code_injection_preserves_indentation() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("test.py");
    let code = "def foo():\n    # refactor: implement\n    pass\n";
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 2).unwrap();
    assert_eq!(ctx.indentation, "    ");

    let generated = "x = 1\ny = 2";
    phantom_core::code_injector::inject_code(
        &file_path_str,
        2,
        generated,
        &ctx.indentation,
        ctx.line_ending,
    )
    .unwrap();

    let result = std::fs::read_to_string(&file_path).unwrap();
    assert!(result.contains("    x = 1"));
    assert!(result.contains("    y = 2"));
    assert!(!result.contains("# refactor: implement"));
}

#[test]
fn test_code_injection_nonexistent_file_errors() {
    let result = phantom_core::code_injector::inject_code(
        "/nonexistent/path/file.py",
        1,
        "print('hello')",
        "",
        phantom_core::code_context::LineEnding::LF,
    );
    assert!(result.is_err());
}

#[test]
fn test_code_injection_empty_generated_code() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("test.py");
    let code = "def foo():\n    pass\n";
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let result = phantom_core::code_injector::inject_code(
        &file_path_str,
        1,
        "",
        "    ",
        phantom_core::code_context::LineEnding::LF,
    );
    assert!(result.is_ok());
    // The line should be replaced with empty
    let result_content = std::fs::read_to_string(&file_path).unwrap();
    assert!(result_content.contains("pass"));
}

#[test]
fn test_code_injection_preserves_other_lines() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("test.rs");
    let code = "fn main() {\n    // refactor: add logic\n    println!(\"hello\");\n}\n";
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    phantom_core::code_injector::inject_code(
        &file_path_str,
        2,
        "let x = 42;",
        "    ",
        phantom_core::code_context::LineEnding::LF,
    )
    .unwrap();

    let result = std::fs::read_to_string(&file_path).unwrap();
    assert!(result.contains("fn main() {"));
    assert!(result.contains("    let x = 42;"));
    assert!(result.contains("    println!(\"hello\");"));
    assert!(result.contains("}"));
    assert!(!result.contains("// refactor: add logic"));
}

#[test]
fn test_plaintext_fallback() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("readme.txt");
    let content = "This is a text file.\nIt has no code structure.\n";
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(content.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 1).unwrap();
    assert_eq!(ctx.language, "plaintext");
    assert!(ctx.enclosing_function.is_none());
    assert!(ctx.enclosing_class.is_none());
}

#[test]
fn test_nonexistent_file_errors() {
    let result = phantom_core::code_context::extract_code_context("/nonexistent/file.py", 1);
    assert!(result.is_err());
}

#[test]
fn test_empty_file_context() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("empty.py");
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(b"").unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 1).unwrap();
    assert_eq!(ctx.language, "python");
    assert!(ctx.enclosing_function.is_none());
    assert!(ctx.imports.is_empty());
}

#[test]
fn test_c_sharp_context_extraction() {
    let dir = tempdir().unwrap();
    let file_path = dir.path().join("Program.cs");
    let cs_code = r#"using System;
using System.Collections.Generic;

namespace MyApp {
    class Program {
        static void Main(string[] args) {
            // refactor: add async main
            Console.WriteLine("Hello");
        }
    }
}
"#;
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(cs_code.as_bytes()).unwrap();
    }
    let file_path_str = file_path.to_string_lossy().to_string();
    let ctx = phantom_core::code_context::extract_code_context(&file_path_str, 8).unwrap();
    assert_eq!(ctx.language, "c_sharp");
    assert!(ctx.imports.iter().any(|i| i.contains("using System;")));
}
