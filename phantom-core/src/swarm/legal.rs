// phantom-core/src/swarm/legal.rs — v3 with CUAD risk detection (41 categories)
// Based on claude-legal-skill + legal-redline-tools from evolsb
// CUAD = Contract Understanding Atticus Dataset — 510 real contracts, 41 risk categories
use crate::document_context::DocumentContext;
use crate::plugin::SwarmAgent;

/// The 41 CUAD risk categories mapped to keyword detectors.
/// Each entry: (category_name, risk_level, trigger_keywords)
const CUAD_CATEGORIES: &[(&str, &str, &[&str])] = &[
    (
        "Automatic Renewal",
        "MEDIUM",
        &[
            "automatically renew",
            "auto-renew",
            "shall renew",
            "unless terminated",
            "notice of non-renewal",
        ],
    ),
    (
        "Governing Law",
        "LOW",
        &[
            "governed by",
            "governing law",
            "laws of the state",
            "jurisdiction of",
        ],
    ),
    (
        "Most Favored Nation",
        "HIGH",
        &["most favored", "best price", "no less favorable", "mfn"],
    ),
    (
        "Non-Compete",
        "HIGH",
        &[
            "non-compete",
            "not compete",
            "covenant not to compete",
            "competitive activity",
        ],
    ),
    (
        "Unlimited Liability",
        "HIGH",
        &[
            "without limitation",
            "unlimited liability",
            "full liability",
            "not limited to",
        ],
    ),
    (
        "IP Ownership Assignment",
        "HIGH",
        &[
            "assigns",
            "all intellectual property",
            "work made for hire",
            "ip assignment",
            "ownership of developments",
        ],
    ),
    (
        "Liquidated Damages",
        "HIGH",
        &[
            "liquidated damages",
            "agreed damages",
            "penalty clause",
            "stipulated sum",
        ],
    ),
    (
        "Termination for Convenience",
        "MEDIUM",
        &[
            "terminate for convenience",
            "terminate without cause",
            "at will termination",
            "upon written notice",
        ],
    ),
    (
        "Change of Control",
        "HIGH",
        &[
            "change of control",
            "acquisition",
            "merger",
            "majority ownership",
            "controlling interest",
        ],
    ),
    (
        "Indemnification",
        "HIGH",
        &[
            "indemnif",
            "defend and hold harmless",
            "indemnitor",
            "indemnified party",
        ],
    ),
    (
        "Limitation of Liability",
        "MEDIUM",
        &[
            "limitation of liability",
            "liability cap",
            "aggregate liability",
            "shall not exceed",
        ],
    ),
    (
        "Price Restriction",
        "MEDIUM",
        &[
            "price restriction",
            "price cap",
            "maximum price",
            "price increase",
        ],
    ),
    (
        "Audit Rights",
        "LOW",
        &[
            "audit rights",
            "right to audit",
            "books and records",
            "inspection rights",
        ],
    ),
    (
        "Exclusivity",
        "HIGH",
        &[
            "exclusive",
            "sole supplier",
            "exclusivity period",
            "not engage with competitors",
        ],
    ),
    (
        "Warranty Duration",
        "LOW",
        &[
            "warranty period",
            "warranty term",
            "warranted for",
            "warranty of",
        ],
    ),
    (
        "Source Code Escrow",
        "MEDIUM",
        &[
            "source code escrow",
            "escrow agent",
            "escrow agreement",
            "source code deposit",
        ],
    ),
    (
        "Anti-Assignment",
        "MEDIUM",
        &[
            "may not assign",
            "without prior written consent",
            "assignment prohibited",
            "not assignable",
        ],
    ),
    (
        "Revenue/Profit Sharing",
        "HIGH",
        &[
            "revenue share",
            "profit sharing",
            "revenue percentage",
            "royalty",
        ],
    ),
    (
        "Minimum Commitment",
        "MEDIUM",
        &[
            "minimum purchase",
            "minimum commitment",
            "minimum order",
            "guaranteed volume",
        ],
    ),
    (
        "Non-Solicitation",
        "MEDIUM",
        &[
            "non-solicitation",
            "not solicit",
            "poaching",
            "hiring restriction",
        ],
    ),
    (
        "Confidentiality",
        "MEDIUM",
        &[
            "confidential",
            "proprietary information",
            "trade secret",
            "non-disclosure",
        ],
    ),
    (
        "Force Majeure",
        "LOW",
        &[
            "force majeure",
            "act of god",
            "beyond reasonable control",
            "pandemic",
            "natural disaster",
        ],
    ),
    (
        "Arbitration",
        "MEDIUM",
        &[
            "arbitration",
            "binding arbitration",
            "aaa rules",
            "jams",
            "dispute resolution",
        ],
    ),
    (
        "Class Action Waiver",
        "HIGH",
        &[
            "class action waiver",
            "class action",
            "individual basis only",
        ],
    ),
    (
        "Renewal Term",
        "LOW",
        &[
            "renewal term",
            "successive terms",
            "initial term",
            "term of agreement",
        ],
    ),
    (
        "Insurance",
        "LOW",
        &[
            "insurance",
            "general liability insurance",
            "maintain coverage",
            "certificate of insurance",
        ],
    ),
    (
        "Termination for Cause",
        "MEDIUM",
        &[
            "terminate for cause",
            "material breach",
            "cure period",
            "notice of breach",
        ],
    ),
    (
        "Cap on Liability",
        "HIGH",
        &[
            "cap on",
            "not exceed",
            "aggregate cap",
            "liability limited to fees",
        ],
    ),
    (
        "Data Protection/GDPR",
        "HIGH",
        &[
            "gdpr",
            "ccpa",
            "data protection",
            "personal data",
            "data controller",
            "data processor",
        ],
    ),
    (
        "Publicity Rights",
        "LOW",
        &[
            "press release",
            "publicity",
            "reference customer",
            "logo usage",
            "case study",
        ],
    ),
    (
        "SLA/Uptime",
        "MEDIUM",
        &[
            "service level",
            "uptime",
            "availability",
            "sla",
            "99.",
            "service credits",
        ],
    ),
    (
        "Payment Terms",
        "LOW",
        &["net 30", "net 60", "payment due", "invoice", "late payment"],
    ),
    (
        "IP License Grant",
        "MEDIUM",
        &[
            "license grant",
            "grants a license",
            "limited license",
            "non-exclusive license",
        ],
    ),
    (
        "Compliance with Laws",
        "LOW",
        &[
            "comply with applicable",
            "laws and regulations",
            "regulatory compliance",
        ],
    ),
    (
        "Notice Requirements",
        "LOW",
        &[
            "written notice",
            "notice period",
            "days prior notice",
            "notice of",
        ],
    ),
    (
        "Dispute Resolution",
        "MEDIUM",
        &[
            "dispute resolution",
            "mediation",
            "litigation",
            "forum selection",
        ],
    ),
    (
        "Representations & Warranties",
        "MEDIUM",
        &[
            "represents and warrants",
            "representations",
            "warranties",
            "covenants",
        ],
    ),
    (
        "Entire Agreement",
        "LOW",
        &[
            "entire agreement",
            "supersedes all prior",
            "complete agreement",
            "merger clause",
        ],
    ),
    (
        "Amendment",
        "LOW",
        &[
            "amendment",
            "modify this agreement",
            "changes to this agreement",
            "written amendment",
        ],
    ),
    (
        "Waiver",
        "LOW",
        &["waiver", "failure to exercise", "waiver of rights"],
    ),
    (
        "Severability",
        "LOW",
        &[
            "severability",
            "severable",
            "if any provision",
            "unenforceable provision",
        ],
    ),
];

pub struct LegalPlusAgent;

/// CUAD Risk Scanner: detects contract risk categories from document text
pub struct CuadScanner;

impl CuadScanner {
    /// Scans document text for CUAD risk categories.
    /// Returns a formatted risk report.
    pub fn scan(text: &str) -> String {
        let lower = text.to_lowercase();
        let mut findings: Vec<(&str, &str, Vec<&str>)> = Vec::new();

        for (category, risk_level, keywords) in CUAD_CATEGORIES {
            let matched: Vec<&str> = keywords
                .iter()
                .filter(|kw| lower.contains(*kw))
                .copied()
                .collect();
            if !matched.is_empty() {
                findings.push((category, risk_level, matched));
            }
        }

        if findings.is_empty() {
            return "## CUAD Risk Scan\nNo high-risk clauses detected. Document may be too short or non-contractual.".to_string();
        }

        // Sort by risk: HIGH first, then MEDIUM, then LOW
        findings.sort_by(|a, b| {
            let weight = |r: &str| match r {
                "HIGH" => 0,
                "MEDIUM" => 1,
                _ => 2,
            };
            weight(a.1).cmp(&weight(b.1))
        });

        let high_count = findings.iter().filter(|f| f.1 == "HIGH").count();
        let medium_count = findings.iter().filter(|f| f.1 == "MEDIUM").count();
        let low_count = findings.iter().filter(|f| f.1 == "LOW").count();

        let mut report = format!(
            "## CUAD Contract Risk Analysis ({}/41 categories detected)\n\
             🔴 HIGH Risk: {} | 🟡 MEDIUM Risk: {} | 🟢 LOW Risk: {}\n\n",
            findings.len(),
            high_count,
            medium_count,
            low_count
        );

        for (category, risk, triggers) in &findings {
            let icon = match *risk {
                "HIGH" => "🔴",
                "MEDIUM" => "🟡",
                _ => "🟢",
            };
            report.push_str(&format!(
                "{} **{}** ({})\n  Triggers: {}\n\n",
                icon,
                category,
                risk,
                triggers.join(", ")
            ));
        }

        report.push_str("\n[LEGAL DISCLAIMER: This is an automated risk scan, not legal advice. Have qualified legal counsel review before signing.]\n");
        report
    }

    /// Generate lawyer-ready redline suggestions for detected risks
    pub fn generate_redlines(text: &str) -> Vec<String> {
        let lower = text.to_lowercase();
        let mut redlines = Vec::new();

        // High-risk patterns with suggested redlines
        let redline_rules = [
            ("unlimited liability", "REDLINE: Add liability cap — suggest 'Notwithstanding the foregoing, aggregate liability shall not exceed the fees paid in the preceding 12 months.'"),
            ("automatically renew", "REDLINE: Extend auto-renewal notice window — suggest '90 days' written notice instead of standard 30."),
            ("work made for hire", "REDLINE: Clarify IP ownership scope — ensure 'pre-existing IP' is carved out with 'excluding any pre-existing materials owned by Contractor.'"),
            ("non-compete", "REDLINE: Limit geographic scope and duration — add 'within [geography] for a period not to exceed [12 months].'"),
            ("assigns", "REDLINE: Add anti-assignment carveout — 'This Agreement may not be assigned without prior written consent, not to be unreasonably withheld.'"),
        ];

        for (pattern, suggestion) in &redline_rules {
            if lower.contains(pattern) {
                redlines.push(suggestion.to_string());
            }
        }

        redlines
    }
}

impl SwarmAgent for LegalPlusAgent {
    fn id(&self) -> &str {
        "legal"
    }
    fn name(&self) -> &str {
        "Legal Document Specialist"
    }
    fn capability(&self) -> crate::plugin::DomainCapability {
        crate::plugin::DomainCapability::Real
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();

        // Run CUAD scan if document is substantial
        let cuad_report = if doc_ctx.full_text.len() > 200 {
            let scan = CuadScanner::scan(&doc_ctx.full_text);
            let redlines = CuadScanner::generate_redlines(&doc_ctx.full_text);
            let redline_str = if redlines.is_empty() {
                String::new()
            } else {
                format!("\n\n### Suggested Redlines\n{}", redlines.join("\n"))
            };
            format!("\n\n### PRE-COMPUTED RISK ANALYSIS\n{scan}{redline_str}")
        } else {
            String::new()
        };

        format!(
            "{base}\n\n[DOCUMENT INTELLIGENCE]\n{doc_fragment}{cuad_report}\n\n*** SWARM ROLE: LEGAL DOCUMENT AGENT ***\n\
            \n## LEGAL INTELLIGENCE RULES\n\
            You assist with legal document DRAFTING only (NOT legal advice). \
            Always append disclaimer at end of any substantive draft.\n\
            \n## PRECISION STANDARDS\n\
            - Use precise, unambiguous language — avoid 'may', prefer 'shall' or 'must'.\n\
            - Define terms on first use: 'the Service Provider (hereinafter \"Provider\")'.\n\
            - Structure: Recitals → Definitions → Obligations → Representations → Remedies → Governing Law.\n\
            - Indemnification: specify scope, exclusions, and caps clearly.\n\
            - Jurisdiction: always specify governing law and dispute resolution forum.\n\
            - NDA/Confidentiality: define what IS confidential (not just what isn't).\n\
            \n## DOCUMENT TYPES\n\
            - NDA: include mutual vs. one-way, term, permitted disclosure, return of materials.\n\
            - SaaS Agreement: uptime SLA, data ownership, GDPR/CCPA, auto-renewal, termination.\n\
            - Employment: at-will vs. fixed term, IP assignment, non-compete (check local law), PIIA.\n\
            - Term Sheet: pre-money valuation, liquidation preferences, pro-rata rights, drag-along.\n\
            - MSA/SOW: acceptance criteria, payment terms, change order process, limitation of liability.\n\
            \n## COMMON CLAUSES LIBRARY\n\
            Force Majeure: 'Neither party shall be liable for any failure or delay in performance \
            resulting from causes beyond its reasonable control, including acts of God, war, \
            pandemic, government action, or network failures.'\n\
            Limitation of Liability: 'In no event shall either party be liable for indirect, \
            incidental, special, exemplary, or consequential damages.'\n\
            Entire Agreement: 'This Agreement constitutes the entire agreement between the parties \
            and supersedes all prior negotiations, representations, or agreements.'\n\
            \n## OUTPUT FORMAT\n\
            Structure documents with numbered sections and subsections (1.1, 1.2, etc.).\n\
            Use CAPS for defined terms after first definition.\n\
            Append: [LEGAL DISCLAIMER: This draft is for reference only — review with qualified legal counsel.]\n\n\
            COMMAND: Execute the user request. START with [REPLACE] if replacing document text."
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("contract")
            || p.contains("agreement")
            || p.contains("legal")
            || p.contains("nda")
            || p.contains("clause")
            || p.contains("indemnif")
            || p.contains("license")
            || p.contains("liability")
            || p.contains("terms of service")
            || p.contains("privacy policy")
            || p.contains("msa")
            || p.contains("sow")
            || p.contains("term sheet")
            || p.contains("employment")
            || p.contains("cuad")
            || p.contains("redline")
            || p.contains("review this contract")
        {
            92
        } else {
            0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cuad_detects_unlimited_liability() {
        let text = "The vendor shall not be liable and there is no limitation on damages without limitation.";
        let report = CuadScanner::scan(text);
        assert!(report.contains("Unlimited Liability") || report.contains("without limitation"));
    }

    #[test]
    fn test_cuad_detects_auto_renewal() {
        let text = "This agreement shall automatically renew for successive 12-month terms unless terminated.";
        let report = CuadScanner::scan(text);
        assert!(report.contains("Automatic Renewal") || report.contains("automatically renew"));
    }

    #[test]
    fn test_cuad_redlines_generated() {
        let text =
            "The vendor shall indemnify automatically renew and unlimited liability applies.";
        let redlines = CuadScanner::generate_redlines(text);
        assert!(!redlines.is_empty());
    }
}
