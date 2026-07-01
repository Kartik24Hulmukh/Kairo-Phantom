//! Excel Formula Engine — P2.5
//! Explain complex Excel formulas in plain English, or generate formulas from natural language.
//! Triggered when DocKind == Excel and prompt contains formula-related keywords.

use anyhow::Result;
use regex::Regex;

#[derive(Debug, Clone)]
pub struct FormulaExplanation {
    pub formula: String,
    pub plain_english: String,
    pub breakdown: Vec<(String, String)>, // (component, explanation)
}

impl FormulaExplanation {
    pub fn format_for_injection(&self) -> String {
        let mut out = format!("📊 Formula: {}\n\n", self.formula);
        out.push_str(&format!("📖 Plain English:\n{}\n\n", self.plain_english));
        if !self.breakdown.is_empty() {
            out.push_str("🔍 Component breakdown:\n");
            for (comp, desc) in &self.breakdown {
                out.push_str(&format!("  • {comp} → {desc}\n"));
            }
        }
        out
    }
}

pub struct ExcelFormulaEngine;

impl ExcelFormulaEngine {
    pub fn new() -> Self {
        Self
    }

    /// Detect if user prompt is asking about Excel formulas.
    pub fn should_handle(prompt: &str, doc_kind: &str) -> bool {
        if !doc_kind.to_lowercase().contains("excel") {
            return false;
        }
        let kw = [
            "=", "formula", "vlookup", "sumif", "countif", "index", "match", "sum(", "if(",
            "iferror", "xlookup", "average",
        ];
        let pl = prompt.to_lowercase();
        kw.iter().any(|k| pl.contains(k))
    }

    /// Detect if prompt contains an actual formula (starts with =).
    pub fn extract_formula(text: &str) -> Option<String> {
        let re = Regex::new(r"=\s*[A-Za-z]+\s*\(").ok()?;
        // Find first formula-like expression
        for line in text.lines() {
            let t = line.trim();
            if t.starts_with('=') || (t.contains('=') && re.is_match(t)) {
                // Extract from = to end of line or closing paren
                let start = t.find('=').unwrap_or(0);
                return Some(t[start..].trim().to_string());
            }
        }
        None
    }

    /// Explain a formula in plain English with component breakdown.
    pub fn explain(&self, formula: &str) -> FormulaExplanation {
        let clean = formula.trim().trim_start_matches('=');
        let breakdown = self.breakdown_formula(clean);
        let plain_english = self.describe_formula(clean);
        FormulaExplanation {
            formula: formula.to_string(),
            plain_english,
            breakdown,
        }
    }

    /// Generate an LLM-ready prompt for formula generation.
    pub fn build_generation_prompt(&self, user_request: &str) -> String {
        format!(
            "Generate an Excel formula for the following request. \
             Output ONLY the formula starting with = and nothing else. \
             If multiple formulas could work, give the most modern Excel 365 version.\n\n\
             Request: {user_request}"
        )
    }

    fn describe_formula(&self, formula: &str) -> String {
        let fl = formula.to_uppercase();
        // Pattern match common formulas
        if fl.starts_with("VLOOKUP(") {
            "Look up a value in the leftmost column of a table and return a value in the same row from a specified column.".into()
        } else if fl.starts_with("XLOOKUP(") {
            "Search a range or array for a match and return the corresponding item. Modern replacement for VLOOKUP/HLOOKUP.".into()
        } else if fl.starts_with("INDEX(") && fl.contains("MATCH(") {
            "Find a value at the intersection of a row and column, where the row/column numbers are determined by matching criteria.".into()
        } else if fl.starts_with("SUMIF(") {
            "Sum cells that meet a single condition or criterion.".into()
        } else if fl.starts_with("SUMIFS(") {
            "Sum cells that meet multiple conditions or criteria.".into()
        } else if fl.starts_with("COUNTIF(") {
            "Count cells that meet a single condition or criterion.".into()
        } else if fl.starts_with("COUNTIFS(") {
            "Count cells that meet multiple conditions or criteria.".into()
        } else if fl.starts_with("IF(") {
            "Evaluate a condition and return one value if TRUE, another if FALSE.".into()
        } else if fl.starts_with("IFERROR(") {
            "Return a specified value if a formula evaluates to an error; otherwise return the formula result.".into()
        } else if fl.starts_with("AVERAGE(") {
            "Calculate the arithmetic mean of a range of numbers.".into()
        } else if fl.starts_with("SUM(") {
            "Add up all numbers in a specified range.".into()
        } else if fl.starts_with("CONCATENATE(") || fl.starts_with("CONCAT(") || fl.contains("&") {
            "Join (concatenate) two or more text strings into a single string.".into()
        } else if fl.starts_with("TEXT(") {
            "Convert a value to text in a specified number format.".into()
        } else if fl.starts_with("LEFT(") || fl.starts_with("RIGHT(") || fl.starts_with("MID(") {
            "Extract a specified number of characters from a text string.".into()
        } else {
            format!("Excel formula: {formula}")
        }
    }

    fn breakdown_formula(&self, formula: &str) -> Vec<(String, String)> {
        let mut parts = Vec::new();
        // Simple argument extractor — split on top-level commas
        let args = extract_top_level_args(formula);
        let fname = formula.split('(').next().unwrap_or("").to_uppercase();

        match fname.as_str() {
            "VLOOKUP" if args.len() >= 3 => {
                if let Some(a) = args.first() {
                    parts.push((
                        a.trim().into(),
                        "Lookup value — what you're searching for".into(),
                    ));
                }
                if let Some(a) = args.get(1) {
                    parts.push((
                        a.trim().into(),
                        "Table array — the range to search in".into(),
                    ));
                }
                if let Some(a) = args.get(2) {
                    parts.push((
                        a.trim().into(),
                        "Column index — which column to return (1=first)".into(),
                    ));
                }
                if let Some(a) = args.get(3) {
                    parts.push((a.trim().into(), "Match type — FALSE for exact match".into()));
                }
            }
            "XLOOKUP" if args.len() >= 3 => {
                if let Some(a) = args.first() {
                    parts.push((a.trim().into(), "Lookup value".into()));
                }
                if let Some(a) = args.get(1) {
                    parts.push((a.trim().into(), "Lookup array".into()));
                }
                if let Some(a) = args.get(2) {
                    parts.push((a.trim().into(), "Return array".into()));
                }
            }
            "SUMIF" if args.len() >= 2 => {
                if let Some(a) = args.first() {
                    parts.push((a.trim().into(), "Range to evaluate for criteria".into()));
                }
                if let Some(a) = args.get(1) {
                    parts.push((a.trim().into(), "Criteria / condition".into()));
                }
                if let Some(a) = args.get(2) {
                    parts.push((
                        a.trim().into(),
                        "Range to sum (if different from criteria range)".into(),
                    ));
                }
            }
            "IF" if args.len() >= 2 => {
                if let Some(a) = args.first() {
                    parts.push((a.trim().into(), "Condition to test".into()));
                }
                if let Some(a) = args.get(1) {
                    parts.push((a.trim().into(), "Value if condition is TRUE".into()));
                }
                if let Some(a) = args.get(2) {
                    parts.push((a.trim().into(), "Value if condition is FALSE".into()));
                }
            }
            _ => {}
        }
        parts
    }
}

/// Extract top-level arguments from a function call string.
fn extract_top_level_args(formula: &str) -> Vec<String> {
    let inner = match formula.find('(') {
        Some(i) => &formula[i + 1..],
        None => return vec![],
    };
    // Strip trailing )
    let inner = inner.trim_end_matches(')');
    let mut args = Vec::new();
    let mut depth = 0i32;
    let mut current = String::new();
    for ch in inner.chars() {
        match ch {
            '(' => {
                depth += 1;
                current.push(ch);
            }
            ')' => {
                depth -= 1;
                current.push(ch);
            }
            ',' if depth == 0 => {
                args.push(current.trim().to_string());
                current = String::new();
            }
            _ => current.push(ch),
        }
    }
    if !current.trim().is_empty() {
        args.push(current.trim().to_string());
    }
    args
}

impl Default for ExcelFormulaEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_should_handle_excel() {
        assert!(ExcelFormulaEngine::should_handle(
            "explain this =VLOOKUP(A2,B:D,3,FALSE)",
            "Excel"
        ));
        assert!(!ExcelFormulaEngine::should_handle(
            "write an email",
            "Microsoft Word"
        ));
    }

    #[test]
    fn test_extract_formula() {
        let text = "I have this formula:\n=VLOOKUP(A2,Sheet2!B:D,3,FALSE)\nCan you explain it?";
        let f = ExcelFormulaEngine::extract_formula(text);
        assert!(f.is_some());
        assert!(f.unwrap().starts_with('='));
    }

    #[test]
    fn test_explain_vlookup() {
        let engine = ExcelFormulaEngine::new();
        let exp = engine.explain("=VLOOKUP(A2,B:D,3,FALSE)");
        assert!(exp.plain_english.contains("Look up"));
        assert!(!exp.breakdown.is_empty());
    }

    #[test]
    fn test_explain_sumif() {
        let engine = ExcelFormulaEngine::new();
        let exp = engine.explain("=SUMIF(A:A,\"Yes\",B:B)");
        assert!(exp.plain_english.to_lowercase().contains("sum"));
    }

    #[test]
    fn test_generation_prompt() {
        let engine = ExcelFormulaEngine::new();
        let prompt = engine.build_generation_prompt("sum all sales where region is East");
        assert!(prompt.contains("sum all sales"));
        assert!(prompt.starts_with("Generate an Excel formula"));
    }

    #[test]
    fn test_arg_extraction() {
        let args = extract_top_level_args("VLOOKUP(A2,Sheet2!B:D,3,FALSE)");
        assert_eq!(args.len(), 4);
        assert_eq!(args[0], "A2");
        assert_eq!(args[2], "3");
    }
}
