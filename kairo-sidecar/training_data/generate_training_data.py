#!/usr/bin/env python3
"""
generate_training_data.py
=========================
Generates (prompt, response) pairs for fine-tuning KairoDocWriter-3B.

Usage
-----
    python generate_training_data.py [--n 2000] [--seed 42] [--out-dir .]

Outputs
-------
    kairo_docwriter_v1.jsonl           – full dataset
    kairo_docwriter_v1_train.jsonl     – 90 % training split
    kairo_docwriter_v1_eval.jsonl      – 10 % evaluation split

Each record follows the Alpaca instruction format::

    {
        "instruction": "<task description>",
        "input":       "<document context / slot values>",
        "output":      "<valid JSON response per Kairo schema>"
    }
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# 50 high-quality seed examples
# ---------------------------------------------------------------------------

EXAMPLES: List[Dict[str, Any]] = [
    # ── Heading 1 ──────────────────────────────────────────────────────────
    {
        "instruction": "Insert a Heading 1 paragraph titled 'Executive Summary' at the beginning of the document.",
        "input": "Document: Annual Report 2024\nCurrent paragraph count: 0",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 0,
                "text": "Executive Summary",
                "style": "Heading 1",
            }
        ),
    },
    {
        "instruction": "Add a top-level heading 'Introduction' before paragraph 2.",
        "input": "Document: Research Paper\nCurrent paragraph count: 5",
        "output": json.dumps(
            {"action": "insert_paragraph", "index": 2, "text": "Introduction", "style": "Heading 1"}
        ),
    },
    {
        "instruction": "Insert a chapter heading 'Market Analysis' at position 0.",
        "input": "Document: Business Plan 2025\nCurrent paragraph count: 3",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 0,
                "text": "Market Analysis",
                "style": "Heading 1",
            }
        ),
    },
    # ── Heading 2 ──────────────────────────────────────────────────────────
    {
        "instruction": "Insert a Heading 2 subheading 'Background' after paragraph 1.",
        "input": "Document: Thesis Draft\nCurrent paragraph count: 10",
        "output": json.dumps(
            {"action": "insert_paragraph", "index": 2, "text": "Background", "style": "Heading 2"}
        ),
    },
    {
        "instruction": "Add a section heading 'Competitive Landscape' at index 4.",
        "input": "Document: Investor Deck\nCurrent paragraph count: 8",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 4,
                "text": "Competitive Landscape",
                "style": "Heading 2",
            }
        ),
    },
    # ── Heading 3 ──────────────────────────────────────────────────────────
    {
        "instruction": "Insert a Heading 3 titled 'Methodology' at paragraph index 6.",
        "input": "Document: Scientific Report\nCurrent paragraph count: 12",
        "output": json.dumps(
            {"action": "insert_paragraph", "index": 6, "text": "Methodology", "style": "Heading 3"}
        ),
    },
    {
        "instruction": "Add a sub-subsection heading 'Data Collection' after paragraph 9.",
        "input": "Document: PhD Dissertation\nCurrent paragraph count: 20",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 10,
                "text": "Data Collection",
                "style": "Heading 3",
            }
        ),
    },
    # ── List Bullet ─────────────────────────────────────────────────────────
    {
        "instruction": "Insert a bullet list item 'Reduce operational costs by 15%' at position 3.",
        "input": "Document: Q3 Goals\nCurrent paragraph count: 5",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 3,
                "text": "Reduce operational costs by 15%",
                "style": "List Bullet",
            }
        ),
    },
    {
        "instruction": "Add a bullet point 'Improve customer satisfaction scores' at index 7.",
        "input": "Document: OKR Document\nCurrent paragraph count: 9",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 7,
                "text": "Improve customer satisfaction scores",
                "style": "List Bullet",
            }
        ),
    },
    {
        "instruction": "Insert a bullet item 'Launch mobile application in Q2' after paragraph 2.",
        "input": "Document: Product Roadmap\nCurrent paragraph count: 6",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 3,
                "text": "Launch mobile application in Q2",
                "style": "List Bullet",
            }
        ),
    },
    # ── List Number ─────────────────────────────────────────────────────────
    {
        "instruction": "Insert a numbered list item 'Submit funding application' at position 1.",
        "input": "Document: Action Items\nCurrent paragraph count: 4",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 1,
                "text": "Submit funding application",
                "style": "List Number",
            }
        ),
    },
    {
        "instruction": "Add a numbered step 'Configure environment variables' at index 5.",
        "input": "Document: Deployment Guide\nCurrent paragraph count: 10",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 5,
                "text": "Configure environment variables",
                "style": "List Number",
            }
        ),
    },
    {
        "instruction": "Insert numbered item 'Review and sign the contract' at paragraph 0.",
        "input": "Document: Onboarding Checklist\nCurrent paragraph count: 7",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": 0,
                "text": "Review and sign the contract",
                "style": "List Number",
            }
        ),
    },
    # ── Replace paragraph ───────────────────────────────────────────────────
    {
        "instruction": "Replace paragraph 3 text with 'The project was completed on schedule and under budget.'",
        "input": "Document: Project Status Report\nParagraph 3: 'The project was compelted on schedle and undr budget.'",
        "output": json.dumps(
            {
                "action": "replace_paragraph",
                "index": 3,
                "text": "The project was completed on schedule and under budget.",
                "style": "Normal",
            }
        ),
    },
    {
        "instruction": "Correct the spelling in paragraph 7 which reads 'Quaterly revenu targts were achived.'",
        "input": "Document: Financial Summary\nParagraph 7: 'Quaterly revenu targts were achived.'",
        "output": json.dumps(
            {
                "action": "replace_paragraph",
                "index": 7,
                "text": "Quarterly revenue targets were achieved.",
                "style": "Normal",
            }
        ),
    },
    {
        "instruction": "Update paragraph 1 to say 'This document outlines our strategic priorities for 2025.'",
        "input": "Document: Strategic Plan\nParagraph 1: 'This documment outlines our stratgic priorites for 2025.'",
        "output": json.dumps(
            {
                "action": "replace_paragraph",
                "index": 1,
                "text": "This document outlines our strategic priorities for 2025.",
                "style": "Normal",
            }
        ),
    },
    # ── Delete paragraph ────────────────────────────────────────────────────
    {
        "instruction": "Delete paragraph 5 from the document.",
        "input": "Document: Meeting Notes\nCurrent paragraph count: 12",
        "output": json.dumps({"action": "delete_paragraph", "index": 5}),
    },
    {
        "instruction": "Remove the duplicate paragraph at index 9.",
        "input": "Document: Policy Document\nCurrent paragraph count: 15",
        "output": json.dumps({"action": "delete_paragraph", "index": 9}),
    },
    {
        "instruction": "Delete the blank paragraph at position 0.",
        "input": "Document: Cover Letter\nCurrent paragraph count: 8",
        "output": json.dumps({"action": "delete_paragraph", "index": 0}),
    },
    # ── Insert table ─────────────────────────────────────────────────────────
    {
        "instruction": "Insert a 3-column table with headers 'Name', 'Role', 'Department' after paragraph 4.",
        "input": "Document: Team Directory\nCurrent paragraph count: 6",
        "output": json.dumps(
            {
                "action": "insert_table",
                "after_paragraph_index": 4,
                "rows": [
                    ["Name", "Role", "Department"],
                    ["Alice Johnson", "Lead Engineer", "Engineering"],
                    ["Bob Smith", "Product Manager", "Product"],
                    ["Carol White", "UX Designer", "Design"],
                ],
            }
        ),
    },
    {
        "instruction": "Insert a comparison table with columns 'Feature', 'Plan A', 'Plan B' after paragraph 2.",
        "input": "Document: Pricing Comparison\nCurrent paragraph count: 5",
        "output": json.dumps(
            {
                "action": "insert_table",
                "after_paragraph_index": 2,
                "rows": [
                    ["Feature", "Plan A", "Plan B"],
                    ["Storage", "10 GB", "100 GB"],
                    ["Users", "5", "Unlimited"],
                    ["Support", "Email", "24/7 Phone"],
                ],
            }
        ),
    },
    {
        "instruction": "Create a quarterly budget table with columns Q1, Q2, Q3 after paragraph 6.",
        "input": "Document: Annual Budget\nCurrent paragraph count: 10",
        "output": json.dumps(
            {
                "action": "insert_table",
                "after_paragraph_index": 6,
                "rows": [
                    ["Category", "Q1", "Q2", "Q3"],
                    ["Marketing", "$50,000", "$60,000", "$55,000"],
                    ["Engineering", "$120,000", "$130,000", "$125,000"],
                    ["Operations", "$40,000", "$42,000", "$41,000"],
                ],
            }
        ),
    },
    # ── Excel: SUM formula ───────────────────────────────────────────────────
    {
        "instruction": "Write a SUM formula in cell D10 to total the values in D2 through D9.",
        "input": "Workbook: Sales Report.xlsx\nSheet: 'Sheet1'\nCell D10 is currently empty.",
        "output": json.dumps(
            {"action": "write_cell", "sheet": "Sheet1", "cell": "D10", "value": "=SUM(D2:D9)"}
        ),
    },
    {
        "instruction": "Insert a SUM formula in B20 that totals cells B2 to B19.",
        "input": "Workbook: Inventory.xlsx\nSheet: 'Inventory'\nB20 should show total stock count.",
        "output": json.dumps(
            {"action": "write_cell", "sheet": "Inventory", "cell": "B20", "value": "=SUM(B2:B19)"}
        ),
    },
    {
        "instruction": "Add a grand total SUM formula in cell E50 summing E2:E49.",
        "input": "Workbook: Revenue.xlsx\nSheet: 'Monthly'\nE50 is the grand total row.",
        "output": json.dumps(
            {"action": "write_cell", "sheet": "Monthly", "cell": "E50", "value": "=SUM(E2:E49)"}
        ),
    },
    # ── Excel: IF formula ────────────────────────────────────────────────────
    {
        "instruction": "Write an IF formula in C2: if B2 > 1000, show 'High', else 'Low'.",
        "input": "Workbook: KPIs.xlsx\nSheet: 'Dashboard'\nB2 contains a revenue value.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": "Dashboard",
                "cell": "C2",
                "value": '=IF(B2>1000,"High","Low")',
            }
        ),
    },
    {
        "instruction": "Insert an IF formula in D5 that checks if C5 >= 90, returning 'Pass' or 'Fail'.",
        "input": "Workbook: Grades.xlsx\nSheet: 'Results'\nC5 contains a numeric exam score.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": "Results",
                "cell": "D5",
                "value": '=IF(C5>=90,"Pass","Fail")',
            }
        ),
    },
    {
        "instruction": "Write an IF formula in F3: if E3 > 0 write 'Profit', else 'Loss'.",
        "input": "Workbook: FinancialModel.xlsx\nSheet: 'P&L'\nE3 contains net income value.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": "P&L",
                "cell": "F3",
                "value": '=IF(E3>0,"Profit","Loss")',
            }
        ),
    },
    # ── Excel: VLOOKUP formula ───────────────────────────────────────────────
    {
        "instruction": "Write a VLOOKUP in C2 to look up A2 in the Products table (A:D on Sheet2), returning column 3.",
        "input": "Workbook: Orders.xlsx\nSheet: 'Orders'\nA2 contains a product ID.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": "Orders",
                "cell": "C2",
                "value": "=VLOOKUP(A2,Sheet2!A:D,3,FALSE)",
            }
        ),
    },
    {
        "instruction": "Insert a VLOOKUP formula in E5 to find B5 in the employee table (A:F on HR sheet), return column 4.",
        "input": "Workbook: Payroll.xlsx\nSheet: 'Payroll'\nB5 contains employee ID.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": "Payroll",
                "cell": "E5",
                "value": "=VLOOKUP(B5,HR!A:F,4,FALSE)",
            }
        ),
    },
    {
        "instruction": "Add a VLOOKUP in D3 to match A3 against the lookup range (A2:C100 on Lookup sheet), returning column 2.",
        "input": "Workbook: Catalog.xlsx\nSheet: 'Summary'\nA3 holds a SKU code.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": "Summary",
                "cell": "D3",
                "value": "=VLOOKUP(A3,Lookup!A2:C100,2,FALSE)",
            }
        ),
    },
    # ── PPTX: update slide title ──────────────────────────────────────────────
    {
        "instruction": "Update the title of slide 1 to 'Q4 2024 Business Review'.",
        "input": "Presentation: Company Update.pptx\nSlide 1 current title: 'Q3 2024 Business Review'",
        "output": json.dumps(
            {"action": "update_slide_title", "slide_index": 0, "title": "Q4 2024 Business Review"}
        ),
    },
    {
        "instruction": "Change the title of slide 3 to 'Product Roadmap 2025'.",
        "input": "Presentation: Strategy Deck.pptx\nSlide 3 current title: 'Product Roadmap 2024'",
        "output": json.dumps(
            {"action": "update_slide_title", "slide_index": 2, "title": "Product Roadmap 2025"}
        ),
    },
    {
        "instruction": "Set the title on slide 5 to 'Thank You & Questions'.",
        "input": "Presentation: Investor Pitch.pptx\nSlide 5 is a closing slide.",
        "output": json.dumps(
            {"action": "update_slide_title", "slide_index": 4, "title": "Thank You & Questions"}
        ),
    },
    # ── PPTX: write bullets ≤ 7 words ─────────────────────────────────────────
    {
        "instruction": "Add three bullet points to slide 2: 'Revenue up 20%', 'Costs down 10%', 'Market share grew'.",
        "input": "Presentation: Quarterly Results.pptx\nSlide 2: financial highlights slide.",
        "output": json.dumps(
            {
                "action": "update_slide_bullets",
                "slide_index": 1,
                "bullets": ["Revenue up 20%", "Costs down 10%", "Market share grew"],
            }
        ),
    },
    {
        "instruction": "Write bullets for slide 4: 'Fast setup', 'Zero configuration needed', 'Scales automatically'.",
        "input": "Presentation: Product Demo.pptx\nSlide 4: key benefits slide.",
        "output": json.dumps(
            {
                "action": "update_slide_bullets",
                "slide_index": 3,
                "bullets": ["Fast setup", "Zero configuration needed", "Scales automatically"],
            }
        ),
    },
    {
        "instruction": "Set bullets on slide 6 to: 'Open source', 'MIT licensed', 'Active community'.",
        "input": "Presentation: Tech Stack.pptx\nSlide 6: open source tooling slide.",
        "output": json.dumps(
            {
                "action": "update_slide_bullets",
                "slide_index": 5,
                "bullets": ["Open source", "MIT licensed", "Active community"],
            }
        ),
    },
    # ── Mixed / contextual examples ───────────────────────────────────────────
    {
        "instruction": "Insert a Heading 2 'Financial Results' followed by a bullet 'Net income increased by 8%' at index 10.",
        "input": "Document: Annual Report 2024\nCurrent paragraph count: 15",
        "output": json.dumps(
            [
                {
                    "action": "insert_paragraph",
                    "index": 10,
                    "text": "Financial Results",
                    "style": "Heading 2",
                },
                {
                    "action": "insert_paragraph",
                    "index": 11,
                    "text": "Net income increased by 8%",
                    "style": "List Bullet",
                },
            ]
        ),
    },
    {
        "instruction": "Replace the incorrect heading at paragraph 0 with 'Global Market Outlook 2025'.",
        "input": "Document: Market Report\nParagraph 0 (Heading 1): 'Globel Markit Outlooke 2024'",
        "output": json.dumps(
            {
                "action": "replace_paragraph",
                "index": 0,
                "text": "Global Market Outlook 2025",
                "style": "Heading 1",
            }
        ),
    },
    {
        "instruction": "Write the label 'Total Revenue' in cell A10 and a SUM formula =SUM(A2:A9) in cell B10.",
        "input": "Workbook: Sales.xlsx\nSheet: 'Monthly Sales'\nRows 2-9 contain monthly figures.",
        "output": json.dumps(
            [
                {
                    "action": "write_cell",
                    "sheet": "Monthly Sales",
                    "cell": "A10",
                    "value": "Total Revenue",
                },
                {
                    "action": "write_cell",
                    "sheet": "Monthly Sales",
                    "cell": "B10",
                    "value": "=SUM(B2:B9)",
                },
            ]
        ),
    },
    {
        "instruction": "Insert a numbered list of three steps: 'Plan', 'Execute', 'Review' starting at index 3.",
        "input": "Document: Project Framework\nCurrent paragraph count: 5",
        "output": json.dumps(
            [
                {"action": "insert_paragraph", "index": 3, "text": "Plan", "style": "List Number"},
                {
                    "action": "insert_paragraph",
                    "index": 4,
                    "text": "Execute",
                    "style": "List Number",
                },
                {
                    "action": "insert_paragraph",
                    "index": 5,
                    "text": "Review",
                    "style": "List Number",
                },
            ]
        ),
    },
    {
        "instruction": "Delete paragraphs 8, 9, and 10 which are duplicate entries.",
        "input": "Document: Specification\nCurrent paragraph count: 20",
        "output": json.dumps(
            [
                {"action": "delete_paragraph", "index": 10},
                {"action": "delete_paragraph", "index": 9},
                {"action": "delete_paragraph", "index": 8},
            ]
        ),
    },
    {
        "instruction": "Insert a Heading 1 'Appendix' at the end of the document (index 25).",
        "input": "Document: Technical Manual\nCurrent paragraph count: 25",
        "output": json.dumps(
            {"action": "insert_paragraph", "index": 25, "text": "Appendix", "style": "Heading 1"}
        ),
    },
    {
        "instruction": "Insert a risks table after paragraph 5 with headers: 'Risk', 'Likelihood', 'Impact'.",
        "input": "Document: Risk Register\nCurrent paragraph count: 8",
        "output": json.dumps(
            {
                "action": "insert_table",
                "after_paragraph_index": 5,
                "rows": [
                    ["Risk", "Likelihood", "Impact"],
                    ["Data breach", "Low", "High"],
                    ["Key staff departure", "Medium", "Medium"],
                    ["Budget overrun", "Medium", "High"],
                ],
            }
        ),
    },
    {
        "instruction": "Write an AVERAGEIF formula in G2 that averages column F values where column A equals 'North'.",
        "input": "Workbook: RegionalSales.xlsx\nSheet: 'Data'\nColumn A has region names, Column F has sales values.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": "Data",
                "cell": "G2",
                "value": '=AVERAGEIF(A:A,"North",F:F)',
            }
        ),
    },
    {
        "instruction": "Update slide 2 title to 'Key Achievements' and add bullets: 'Shipped v2.0', 'Grew team 30%', '99.9% uptime'.",
        "input": "Presentation: Year in Review.pptx\nSlide 2 is currently titled 'Highlights'.",
        "output": json.dumps(
            [
                {"action": "update_slide_title", "slide_index": 1, "title": "Key Achievements"},
                {
                    "action": "update_slide_bullets",
                    "slide_index": 1,
                    "bullets": ["Shipped v2.0", "Grew team 30%", "99.9% uptime"],
                },
            ]
        ),
    },
    {
        "instruction": "Insert a Heading 3 'Statistical Analysis' at index 14 and a Normal paragraph below it.",
        "input": "Document: Research Paper\nParagraph 14 will follow the methodology section.",
        "output": json.dumps(
            [
                {
                    "action": "insert_paragraph",
                    "index": 14,
                    "text": "Statistical Analysis",
                    "style": "Heading 3",
                },
                {
                    "action": "insert_paragraph",
                    "index": 15,
                    "text": "We applied multivariate regression analysis to the collected dataset.",
                    "style": "Normal",
                },
            ]
        ),
    },
]

# ---------------------------------------------------------------------------
# Template variation helpers
# ---------------------------------------------------------------------------

_HEADING_TEXTS: Dict[str, List[str]] = {
    "Heading 1": [
        "Executive Summary",
        "Introduction",
        "Overview",
        "Background",
        "Conclusion",
        "Appendix",
        "Market Analysis",
        "Financial Results",
        "Strategic Vision",
        "Risk Assessment",
        "Recommendations",
        "Methodology",
        "Scope of Work",
        "Project Objectives",
    ],
    "Heading 2": [
        "Background",
        "Current State",
        "Proposed Solution",
        "Implementation Plan",
        "Key Findings",
        "Cost Analysis",
        "Timeline",
        "Resource Requirements",
        "Competitive Landscape",
        "SWOT Analysis",
        "Risk Factors",
    ],
    "Heading 3": [
        "Data Collection",
        "Statistical Analysis",
        "Survey Results",
        "Interview Findings",
        "Case Study",
        "Technical Specifications",
        "Integration Points",
        "Testing Approach",
        "Deployment Steps",
    ],
}

_BULLET_TEXTS = [
    "Reduce operational costs by {pct}%",
    "Increase revenue by {pct}% year-over-year",
    "Improve customer satisfaction scores",
    "Launch {product} in {quarter}",
    "Hire {n} new engineers by end of Q{q}",
    "Complete security audit",
    "Migrate to cloud infrastructure",
    "Achieve ISO {n} certification",
    "Expand into {region} market",
    "Reduce churn rate by {pct}%",
]

_PRODUCTS = ["mobile app", "API v3", "web portal", "analytics dashboard", "AI assistant"]
_REGIONS = ["European", "Asian", "Latin American", "Middle Eastern", "Southeast Asian"]
_QUARTERS = ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025"]
_DOCS = [
    "Annual Report",
    "Project Charter",
    "Business Plan",
    "Research Paper",
    "Technical Spec",
    "Meeting Notes",
    "Policy Document",
    "User Manual",
]
_SHEETS = ["Sheet1", "Data", "Summary", "Report", "Dashboard", "Monthly", "Q4"]
_WORKBOOKS = [
    "Sales Report.xlsx",
    "Budget.xlsx",
    "Inventory.xlsx",
    "KPIs.xlsx",
    "Revenue.xlsx",
    "Payroll.xlsx",
]
_PRESENTATIONS = [
    "Investor Pitch.pptx",
    "Strategy Deck.pptx",
    "Quarterly Review.pptx",
    "Product Demo.pptx",
]


def _rand_pct(rng: random.Random) -> int:
    return rng.choice([5, 8, 10, 12, 15, 20, 25, 30])


def _rand_n(rng: random.Random) -> int:
    return rng.randint(2, 50)


def _expand_bullet(tmpl: str, rng: random.Random) -> str:
    return tmpl.format(
        pct=_rand_pct(rng),
        product=rng.choice(_PRODUCTS),
        quarter=rng.choice(_QUARTERS),
        n=_rand_n(rng),
        q=rng.randint(1, 4),
        region=rng.choice(_REGIONS),
    )


def _make_heading_example(rng: random.Random) -> Dict[str, Any]:
    level = rng.randint(1, 3)
    style = f"Heading {level}"
    text = rng.choice(_HEADING_TEXTS[style])
    index = rng.randint(0, 20)
    doc = rng.choice(_DOCS)
    count = rng.randint(index, index + 30)
    return {
        "instruction": f"Insert a {style} titled '{text}' at paragraph index {index}.",
        "input": f"Document: {doc}\nCurrent paragraph count: {count}",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": index,
                "text": text,
                "style": style,
            }
        ),
    }


def _make_bullet_example(rng: random.Random) -> Dict[str, Any]:
    is_numbered = rng.random() < 0.4
    style = "List Number" if is_numbered else "List Bullet"
    tmpl = rng.choice(_BULLET_TEXTS)
    text = _expand_bullet(tmpl, rng)
    index = rng.randint(1, 15)
    doc = rng.choice(_DOCS)
    count = rng.randint(index, index + 20)
    list_kind = "numbered" if is_numbered else "bullet"
    return {
        "instruction": f"Insert a {list_kind} list item '{text}' at index {index}.",
        "input": f"Document: {doc}\nCurrent paragraph count: {count}",
        "output": json.dumps(
            {
                "action": "insert_paragraph",
                "index": index,
                "text": text,
                "style": style,
            }
        ),
    }


def _make_replace_example(rng: random.Random) -> Dict[str, Any]:
    corrections = [
        ("Quaterly revenu targts were achived.", "Quarterly revenue targets were achieved."),
        ("The projcet delivrables are on shedule.", "The project deliverables are on schedule."),
        ("Custmer satifaction has incrased.", "Customer satisfaction has increased."),
        ("Net proffit margn improvd significntly.", "Net profit margin improved significantly."),
        ("All complience reqirments have ben met.", "All compliance requirements have been met."),
    ]
    wrong, correct = rng.choice(corrections)
    index = rng.randint(0, 20)
    doc = rng.choice(_DOCS)
    return {
        "instruction": f"Correct the spelling in paragraph {index}: '{wrong}'",
        "input": f"Document: {doc}\nParagraph {index}: '{wrong}'",
        "output": json.dumps(
            {
                "action": "replace_paragraph",
                "index": index,
                "text": correct,
                "style": "Normal",
            }
        ),
    }


def _make_delete_example(rng: random.Random) -> Dict[str, Any]:
    index = rng.randint(0, 25)
    doc = rng.choice(_DOCS)
    count = rng.randint(index + 1, index + 30)
    reasons = [
        "Delete paragraph {i} which is a duplicate.",
        "Remove the blank paragraph at index {i}.",
        "Delete the outdated content at paragraph {i}.",
        "Remove paragraph {i} as it is no longer relevant.",
    ]
    instruction = rng.choice(reasons).format(i=index)
    return {
        "instruction": instruction,
        "input": f"Document: {doc}\nCurrent paragraph count: {count}",
        "output": json.dumps({"action": "delete_paragraph", "index": index}),
    }


def _make_table_example(rng: random.Random) -> Dict[str, Any]:
    table_templates = [
        {
            "cols": ["Name", "Role", "Department"],
            "rows": [["Alice Johnson", "Engineer", "Engineering"], ["Bob Smith", "PM", "Product"]],
        },
        {
            "cols": ["Risk", "Likelihood", "Impact"],
            "rows": [["Data breach", "Low", "High"], ["Budget overrun", "Medium", "High"]],
        },
        {
            "cols": ["Feature", "Basic", "Premium"],
            "rows": [["Storage", "5 GB", "100 GB"], ["Support", "Email", "24/7"]],
        },
        {
            "cols": ["Quarter", "Revenue", "Expenses", "Profit"],
            "rows": [["Q1", "$1.2M", "$0.9M", "$0.3M"], ["Q2", "$1.5M", "$1.0M", "$0.5M"]],
        },
    ]
    tmpl = rng.choice(table_templates)
    after = rng.randint(0, 15)
    doc = rng.choice(_DOCS)
    count = rng.randint(after + 1, after + 20)
    col_str = ", ".join(f"'{c}'" for c in tmpl["cols"])
    return {
        "instruction": f"Insert a table with columns {col_str} after paragraph {after}.",
        "input": f"Document: {doc}\nCurrent paragraph count: {count}",
        "output": json.dumps(
            {
                "action": "insert_table",
                "after_paragraph_index": after,
                "rows": [tmpl["cols"]] + tmpl["rows"],
            }
        ),
    }


def _make_excel_sum_example(rng: random.Random) -> Dict[str, Any]:
    col = rng.choice(["B", "C", "D", "E", "F", "G"])
    start_row = 2
    end_row = rng.randint(5, 50)
    total_row = end_row + 1
    sheet = rng.choice(_SHEETS)
    wb = rng.choice(_WORKBOOKS)
    return {
        "instruction": f"Write a SUM formula in {col}{total_row} to total {col}{start_row}:{col}{end_row}.",
        "input": f"Workbook: {wb}\nSheet: '{sheet}'\nRows {start_row}-{end_row} contain numeric values.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": sheet,
                "cell": f"{col}{total_row}",
                "value": f"=SUM({col}{start_row}:{col}{end_row})",
            }
        ),
    }


def _make_excel_if_example(rng: random.Random) -> Dict[str, Any]:
    check_col = rng.choice(["A", "B", "C", "D", "E"])
    result_col = rng.choice(["F", "G", "H"])
    row = rng.randint(2, 20)
    threshold = rng.choice([0, 50, 100, 500, 1000, 10000])
    true_val, false_val = rng.choice(
        [
            ("Pass", "Fail"),
            ("Yes", "No"),
            ("High", "Low"),
            ("Approved", "Rejected"),
            ("Profit", "Loss"),
        ]
    )
    op = rng.choice([">", ">=", "<", "<="])
    sheet = rng.choice(_SHEETS)
    wb = rng.choice(_WORKBOOKS)
    return {
        "instruction": (
            f"Write an IF formula in {result_col}{row}: "
            f"if {check_col}{row} {op} {threshold}, show '{true_val}', else '{false_val}'."
        ),
        "input": f"Workbook: {wb}\nSheet: '{sheet}'\n{check_col}{row} contains a numeric value.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": sheet,
                "cell": f"{result_col}{row}",
                "value": f'=IF({check_col}{row}{op}{threshold},"{true_val}","{false_val}")',
            }
        ),
    }


def _make_excel_vlookup_example(rng: random.Random) -> Dict[str, Any]:
    key_col = rng.choice(["A", "B", "C"])
    result_col = rng.choice(["D", "E", "F", "G"])
    row = rng.randint(2, 20)
    ref_sheet = rng.choice(["Lookup", "Reference", "Products", "HR", "Catalog"])
    table_range = "A:D" if rng.random() > 0.5 else "A2:E100"
    col_index = rng.randint(2, 4)
    sheet = rng.choice(_SHEETS)
    wb = rng.choice(_WORKBOOKS)
    return {
        "instruction": (
            f"Insert a VLOOKUP in {result_col}{row} to look up {key_col}{row} "
            f"in the {ref_sheet} table ({table_range}), returning column {col_index}."
        ),
        "input": f"Workbook: {wb}\nSheet: '{sheet}'\n{key_col}{row} contains an ID value.",
        "output": json.dumps(
            {
                "action": "write_cell",
                "sheet": sheet,
                "cell": f"{result_col}{row}",
                "value": f"=VLOOKUP({key_col}{row},{ref_sheet}!{table_range},{col_index},FALSE)",
            }
        ),
    }


def _make_pptx_title_example(rng: random.Random) -> Dict[str, Any]:
    slide_idx = rng.randint(0, 10)
    titles = [
        "Q{q} {year} Business Review",
        "Product Strategy {year}",
        "Market Opportunity Overview",
        "Key Performance Indicators",
        "Thank You & Questions",
        "Team Introduction",
        "Financial Summary",
        "Technology Roadmap",
    ]
    title = rng.choice(titles).format(
        q=rng.randint(1, 4),
        year=rng.randint(2024, 2026),
    )
    pptx = rng.choice(_PRESENTATIONS)
    return {
        "instruction": f"Update the title of slide {slide_idx + 1} to '{title}'.",
        "input": f"Presentation: {pptx}\nSlide {slide_idx + 1} needs a title update.",
        "output": json.dumps(
            {
                "action": "update_slide_title",
                "slide_index": slide_idx,
                "title": title,
            }
        ),
    }


def _make_pptx_bullets_example(rng: random.Random) -> Dict[str, Any]:
    bullet_pools = [
        ["Revenue up {pct}%", "Costs down {pct}%", "Market share grew"],
        ["Fast setup", "Zero configuration", "Scales automatically"],
        ["Open source", "MIT licensed", "Active community"],
        ["Shipped v{n}.0", "Grew team {pct}%", "99.9% uptime"],
        ["Cut costs {pct}%", "Increased NPS", "Hired {n} engineers"],
    ]
    pool = rng.choice(bullet_pools)
    bullets = [_expand_bullet(b, rng) for b in pool]
    slide_idx = rng.randint(0, 10)
    pptx = rng.choice(_PRESENTATIONS)
    return {
        "instruction": (
            f"Write bullets for slide {slide_idx + 1}: "
            + ", ".join(f"'{b}'" for b in bullets)
            + "."
        ),
        "input": f"Presentation: {pptx}\nSlide {slide_idx + 1} is a key points slide.",
        "output": json.dumps(
            {
                "action": "update_slide_bullets",
                "slide_index": slide_idx,
                "bullets": bullets,
            }
        ),
    }


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

_GENERATORS = [
    (_make_heading_example, 0.18),
    (_make_bullet_example, 0.16),
    (_make_replace_example, 0.12),
    (_make_delete_example, 0.10),
    (_make_table_example, 0.12),
    (_make_excel_sum_example, 0.10),
    (_make_excel_if_example, 0.08),
    (_make_excel_vlookup_example, 0.07),
    (_make_pptx_title_example, 0.04),
    (_make_pptx_bullets_example, 0.03),
]

# Verify weights sum to 1
assert abs(sum(w for _, w in _GENERATORS) - 1.0) < 1e-9, "Generator weights must sum to 1"


def _pick_generator(rng: random.Random):
    r = rng.random()
    cumulative = 0.0
    for fn, weight in _GENERATORS:
        cumulative += weight
        if r < cumulative:
            return fn
    return _GENERATORS[-1][0]


def generate_dataset(n: int = 2000, seed: int = 42) -> List[Dict[str, Any]]:
    """Generate *n* training examples from seed data + template variations."""
    rng = random.Random(seed)

    # Start with all 50 seed examples (shuffled)
    dataset: List[Dict[str, Any]] = list(EXAMPLES)
    rng.shuffle(dataset)

    # Generate synthetic variations to fill up to n
    while len(dataset) < n:
        fn = _pick_generator(rng)
        try:
            example = fn(rng)
            dataset.append(example)
        except Exception:
            pass  # skip malformed examples

    # Shuffle final dataset
    rng.shuffle(dataset)
    return dataset[:n]


def save_dataset(
    dataset: List[Dict[str, Any]],
    out_dir: Path,
    train_ratio: float = 0.9,
) -> None:
    """Save full, train, and eval splits as JSON Lines files."""
    out_dir.mkdir(parents=True, exist_ok=True)

    full_path = out_dir / "kairo_docwriter_v1.jsonl"
    train_path = out_dir / "kairo_docwriter_v1_train.jsonl"
    eval_path = out_dir / "kairo_docwriter_v1_eval.jsonl"

    split_idx = int(len(dataset) * train_ratio)
    train_set = dataset[:split_idx]
    eval_set = dataset[split_idx:]

    for path, data in [
        (full_path, dataset),
        (train_path, train_set),
        (eval_path, eval_set),
    ]:
        with open(path, "w", encoding="utf-8") as fh:
            for record in data:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"Saved {len(data):>6} examples → {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate KairoDocWriter fine-tuning data.")
    parser.add_argument("--n", type=int, default=2000, help="Total examples to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Output directory (default: same directory as this script)",
    )
    args = parser.parse_args()

    print(f"Generating {args.n} training examples (seed={args.seed}) …")
    dataset = generate_dataset(n=args.n, seed=args.seed)
    save_dataset(dataset, out_dir=args.out_dir)
    print("Done.")


if __name__ == "__main__":
    main()
