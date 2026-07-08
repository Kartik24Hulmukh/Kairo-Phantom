# Kairo Phantom — Grounding Benchmark Report

> Model ID: `kairo-test-mode-v1` | Seed: `42` | Corpus Hash: `52ceb0265dfff3ce31604ae98ebadf75a488df1f6993610d4d0ddfc810482060`

> Python: `3.12.12` | Platform: `Linux-x86_64`

## Release Gates

| Gate | Measured | Target | Status | Numerator | Denominator |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Grounded Answer Rate | 96.3855% | ≥95.0% | ✅ PASS | 80 | 83 |
| Refusal On Unanswerable | 100.0% | ≥100.0% | ✅ PASS | 1 | 1 |
| False Refusal Rate | 3.6145% | <5.0% | ✅ PASS | 3 | 83 |
| Ungrounded Render Count | 0 | =0 | ✅ PASS | — | — |

## Per-Pack Breakdown

### Pack: `contract`

| Metric | Value |
| :--- | :--- |
| Total Documents | 3 |
| Answerable Fields | 20 |
| Grounded Answers | 20 |
| Ungrounded Render Count | 0 |
| Grounded-Answer Rate | 100.0% |
| Refusal-on-Unanswerable | 100.0% |
| False-Refusal Rate | 0.0% |

#### Per-Field Accuracy (contract)

| Field | Accuracy |
| :--- | :--- |
| `confidentiality_clause` | 100.0% |
| `effective_date` | 100.0% |
| `governing_law` | 100.0% |
| `obligations` | 100.0% |
| `parties` | 100.0% |
| `payment_terms` | 66.7% |
| `termination_date` | 100.0% |

### Pack: `generic`

| Metric | Value |
| :--- | :--- |
| Total Documents | 3 |
| Answerable Fields | 12 |
| Grounded Answers | 9 |
| Ungrounded Render Count | 0 |
| Grounded-Answer Rate | 75.0% |
| Refusal-on-Unanswerable | 100.0% |
| False-Refusal Rate | 25.0% |

#### Per-Field Accuracy (generic)

| Field | Accuracy |
| :--- | :--- |
| `entities` | 0.0% |
| `key_claims` | 100.0% |
| `summary` | 100.0% |
| `topics` | 100.0% |

### Pack: `invoice`

| Metric | Value |
| :--- | :--- |
| Total Documents | 3 |
| Answerable Fields | 27 |
| Grounded Answers | 27 |
| Ungrounded Render Count | 0 |
| Grounded-Answer Rate | 100.0% |
| Refusal-on-Unanswerable | 100.0% |
| False-Refusal Rate | 0.0% |

#### Per-Field Accuracy (invoice)

| Field | Accuracy |
| :--- | :--- |
| `currency` | 100.0% |
| `due_date` | 100.0% |
| `invoice_date` | 100.0% |
| `invoice_number` | 100.0% |
| `line_items` | 100.0% |
| `payment_terms` | 100.0% |
| `tax_amount` | 100.0% |
| `total_amount` | 100.0% |
| `vendor_name` | 100.0% |

### Pack: `paper`

| Metric | Value |
| :--- | :--- |
| Total Documents | 3 |
| Answerable Fields | 24 |
| Grounded Answers | 24 |
| Ungrounded Render Count | 0 |
| Grounded-Answer Rate | 100.0% |
| Refusal-on-Unanswerable | 100.0% |
| False-Refusal Rate | 0.0% |

#### Per-Field Accuracy (paper)

| Field | Accuracy |
| :--- | :--- |
| `abstract_summary` | 100.0% |
| `authors` | 100.0% |
| `figure_references` | 100.0% |
| `key_claims` | 100.0% |
| `methods` | 100.0% |
| `reported_numbers` | 100.0% |
| `table_references` | 100.0% |
| `title` | 100.0% |

## Per-Document Breakdown

| Fixture | Pack | Grounded% | Refusal% | FalseRef% | Ungrounded |
| :--- | :--- | :--- | :--- | :--- | :--- |
| sample_generic_01 | generic | 75.0% | 100.0% | 25.0% | 0 |
| sample_generic_02 | generic | 75.0% | 100.0% | 25.0% | 0 |
| sample_generic_03 | generic | 75.0% | 100.0% | 25.0% | 0 |
| sample_invoice_01 | invoice | 100.0% | 100.0% | 0.0% | 0 |
| sample_invoice_02 | invoice | 100.0% | 100.0% | 0.0% | 0 |
| sample_invoice_03 | invoice | 100.0% | 100.0% | 0.0% | 0 |
| sample_paper_01 | paper | 100.0% | 100.0% | 0.0% | 0 |
| sample_paper_02 | paper | 100.0% | 100.0% | 0.0% | 0 |
| sample_paper_03 | paper | 100.0% | 100.0% | 0.0% | 0 |
| sample_contract_01 | contract | 100.0% | 100.0% | 0.0% | 0 |
| sample_contract_02 | contract | 100.0% | 100.0% | 0.0% | 0 |
| sample_contract_03 | contract | 100.0% | 100.0% | 0.0% | 0 |

## Per-Document Quality Details

### sample_generic_01 (generic)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| summary | grounded | Kairo Phantom Project Overview Kairo Phantom is a  | Kairo Phantom Project Overview
Kairo Phantom is a  | ✅ | ✅ | exact |
| key_claims | grounded | ['Every extraction must be grounded or it is block | ["Every extraction must be grounded or it is block | ✅ | ✅ | exact |
| entities | false_refusal | ['Kairo Phantom', 'Antigravity Team'] | — | ❌ | ❌ | — |
| topics | grounded | ['technology', 'security', 'intelligence'] | ["technology", "security", "data", "automotive"] | ✅ | ✅ | exact |

### sample_generic_02 (generic)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| summary | grounded | Verifiable RAG Systems in 2026 Standard Retrieval- | Verifiable RAG Systems in 2026
Standard Retrieval- | ✅ | ✅ | exact |
| key_claims | grounded | ['Standard RAG systems suffer from high hallucinat | ["Standard RAG systems suffer from high hallucinat | ✅ | ✅ | exact |
| entities | false_refusal | ['RAG', 'Kairo Phantom', 'DeepMind Team'] | — | ❌ | ❌ | — |
| topics | grounded | ['technology', 'security'] | ["technology", "financial", "automotive"] | ✅ | ✅ | exact |

### sample_generic_03 (generic)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| summary | grounded | Local-First Software Development The local-first s | Local-First Software Development
The local-first s | ✅ | ✅ | exact |
| key_claims | grounded | ['Local-first software provides superior privacy a | ["Local-first software provides superior privacy a | ✅ | ✅ | exact |
| entities | false_refusal | ['Ollama', 'Qdrant Edge', 'Kairo Phantom', 'OSS Co | — | ❌ | ❌ | — |
| topics | grounded | ['technology', 'paper', 'intelligence'] | ["technology", "security", "data", "automotive"] | ✅ | ✅ | exact |

### sample_invoice_01 (invoice)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| vendor_name | grounded | ACME Corp | ACME Corp | ✅ | ✅ | exact |
| invoice_number | grounded | INV-2026-001 | INV-2026-001 | ✅ | ✅ | exact |
| invoice_date | grounded | 2026-06-15 | 2026-06-15 | ✅ | ✅ | exact |
| due_date | grounded | 2026-07-15 | 2026-07-15 | ✅ | ✅ | exact |
| total_amount | grounded | 1250.0 | 1250.00 | ✅ | ✅ | exact |
| currency | grounded | USD | USD | ✅ | ✅ | exact |
| line_items | grounded | [{'description': 'Consulting Services', 'quantity' | [{"description": "Consulting Services", "quantity" | ✅ | ✅ | exact |
| tax_amount | grounded | 0.0 | 0.00 | ✅ | ✅ | exact |
| payment_terms | grounded | Net 30 | Net 30 | ✅ | ✅ | exact |

### sample_invoice_02 (invoice)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| vendor_name | grounded | Globex Corporation | Globex Corporation | ✅ | ✅ | exact |
| invoice_number | grounded | INV-10024 | INV-10024 | ✅ | ✅ | exact |
| invoice_date | grounded | 2026-06-10 | 2026-06-10 | ✅ | ✅ | exact |
| due_date | grounded | 2026-07-10 | 2026-07-10 | ✅ | ✅ | exact |
| total_amount | grounded | 3000.0 | 3000.00 | ✅ | ✅ | exact |
| currency | grounded | USD | USD | ✅ | ✅ | exact |
| line_items | grounded | [{'description': 'Custom Widgets', 'quantity': 5,  | [{"description": "Custom Widgets", "quantity": 5,  | ✅ | ✅ | exact |
| tax_amount | grounded | 50.0 | 50.00 | ✅ | ✅ | exact |
| payment_terms | grounded | Net 30 | Net 30 | ✅ | ✅ | exact |

### sample_invoice_03 (invoice)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| vendor_name | grounded | Initech LLC | Initech LLC | ✅ | ✅ | exact |
| invoice_number | grounded | INV-998877 | INV-998877 | ✅ | ✅ | exact |
| invoice_date | grounded | 2026-06-12 | 2026-06-12 | ✅ | ✅ | exact |
| due_date | grounded | 2026-06-12 | 2026-06-12 | ✅ | ✅ | exact |
| total_amount | grounded | 4320.0 | 4320.00 | ✅ | ✅ | exact |
| currency | grounded | USD | USD | ✅ | ✅ | exact |
| line_items | grounded | [{'description': 'Software Licenses', 'quantity':  | [{"description": "Software Licenses", "quantity":  | ✅ | ✅ | exact |
| tax_amount | grounded | 320.0 | 320.00 | ✅ | ✅ | exact |
| payment_terms | grounded | Due on Receipt | Due on Receipt | ✅ | ✅ | exact |

### sample_paper_01 (paper)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| title | grounded | Attention Is All You Need | Attention Is All You Need | ✅ | ✅ | exact |
| authors | grounded | ['Ashish Vaswani', 'Noam Shazeer', 'Niki Parmar',  | ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar",  | ✅ | ✅ | exact |
| abstract_summary | grounded | We propose a new simple network architecture, the  | We propose a new simple network architecture, the  | ✅ | ✅ | exact |
| key_claims | grounded | ['The Transformer model outperforms recurrent or c | ["The Transformer model outperforms recurrent or c | ✅ | ✅ | exact |
| methods | grounded | ['We used the Transformer architecture with multi- | ["We used the Transformer architecture with multi- | ✅ | ✅ | exact |
| reported_numbers | grounded | ['28.4', '2.0'] | ["28.4", "2.0"] | ✅ | ✅ | exact |
| figure_references | grounded | ['Figure 1', 'Figure 2'] | ["Figure 1", "Figure 2"] | ✅ | ✅ | exact |
| table_references | grounded | ['Table 1', 'Table 2'] | ["Table 1", "Table 2"] | ✅ | ✅ | exact |

### sample_paper_02 (paper)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| title | grounded | LoRA: Low-Rank Adaptation of Large Language Models | LoRA: Low-Rank Adaptation of Large Language Models | ✅ | ✅ | exact |
| authors | grounded | ['Edward J. Hu', 'Yibin Shen', 'Phillip Wallis', ' | ["Edward J. Hu", "Yibin Shen", "Phillip Wallis", " | ✅ | ✅ | exact |
| abstract_summary | grounded | We propose Low-Rank Adaptation, or LoRA, which fre | We propose Low-Rank Adaptation, or LoRA, which fre | ✅ | ✅ | exact |
| key_claims | grounded | ['LoRA reduces the number of trainable parameters  | ["LoRA reduces the number of trainable parameters  | ✅ | ✅ | exact |
| methods | grounded | ['We parameterize the weight updates by representi | ["We parameterize the weight updates by representi | ✅ | ✅ | exact |
| reported_numbers | grounded | ['82.5%', '0.12%'] | ["82.5", "0.12"] | ✅ | ✅ | exact |
| figure_references | grounded | ['Figure 1', 'Figure 3'] | ["Figure 1", "Figure 3"] | ✅ | ✅ | exact |
| table_references | grounded | ['Table 1', 'Table 2'] | ["Table 1", "Table 2"] | ✅ | ✅ | exact |

### sample_paper_03 (paper)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| title | grounded | Retrieval-Augmented Generation for Knowledge-Inten | Retrieval-Augmented Generation for Knowledge-Inten | ✅ | ✅ | exact |
| authors | grounded | ['Patrick Lewis', 'Ethan Perez', 'Aleksandara Pikt | ["Patrick Lewis", "Ethan Perez", "Aleksandara Pikt | ✅ | ✅ | exact |
| abstract_summary | grounded | We introduce Retrieval-Augmented Generation (RAG)  | We introduce Retrieval-Augmented Generation (RAG)  | ✅ | ✅ | exact |
| key_claims | grounded | ['RAG models produce more factual, specific, and d | ["RAG models produce more factual, specific, and d | ✅ | ✅ | exact |
| methods | grounded | ['We combine a dense passage retriever (DPR) with  | ["We combine a dense passage retriever (DPR) with  | ✅ | ✅ | exact |
| reported_numbers | grounded | ['44.5%'] | ["44.5"] | ✅ | ✅ | exact |
| figure_references | grounded | ['Figure 1', 'Figure 2'] | ["Figure 1", "Figure 2"] | ✅ | ✅ | exact |
| table_references | grounded | ['Table 1', 'Table 3'] | ["Table 1", "Table 3"] | ✅ | ✅ | exact |

### sample_contract_01 (contract)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| parties | grounded | ['ACME Corp', 'Client Solutions Inc.'] | ["ACME Corp", "Client Solutions Inc"] | ✅ | ✅ | exact |
| effective_date | grounded | 2026-06-01 | 2026-06-01 | ✅ | ✅ | exact |
| termination_date | grounded | 2029-06-01 | 2029-06-01 | ✅ | ✅ | exact |
| obligations | grounded | ['Licensee shall pay the license fees within 30 da | ["License Grant and Obligations: Licensee shall pa | ✅ | ✅ | fuzzy |
| governing_law | grounded | Delaware | Delaware | ✅ | ✅ | exact |
| payment_terms | grounded | within 30 days | within 30 days | ✅ | ✅ | exact |
| confidentiality_clause | grounded | Each party agrees to maintain confidentiality of a | Each party agrees to maintain confidentiality of a | ✅ | ✅ | exact |

### sample_contract_02 (contract)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| parties | grounded | ['Wayne Enterprises', 'Globex Corporation'] | ["Wayne Enterprises", "Globex Corporation"] | ✅ | ✅ | exact |
| effective_date | grounded | 2026-05-15 | 2026-05-15 | ✅ | ✅ | exact |
| termination_date | grounded | 2027-05-15 | 2027-05-15 | ✅ | ✅ | exact |
| obligations | grounded | ['Consulting Services Agreement is entered into as | ["Services and Obligations: Consultant shall perfo | ✅ | ✅ | fuzzy |
| governing_law | grounded | New York | New York | ✅ | ✅ | exact |
| payment_terms | grounded | within 15 days | within 15 days | ✅ | ✅ | exact |
| confidentiality_clause | grounded | Consultant agrees that all Wayne Enterprises busin | Consultant agrees that all Wayne Enterprises busin | ✅ | ✅ | exact |

### sample_contract_03 (contract)

| Field | Status | Expected | Extracted | Grounded | Rendered | Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| parties | grounded | ['Initech LLC', 'Intertrode Corp'] | ["Initech LLC", "Intertrode Corp"] | ✅ | ✅ | exact |
| effective_date | grounded | 2026-06-12 | 2026-06-12 | ✅ | ✅ | exact |
| termination_date | grounded | 2028-06-12 | 2028-06-12 | ✅ | ✅ | exact |
| obligations | grounded | ['Receiving Party shall use the information solely | ["Obligations: Receiving Party shall use the infor | ✅ | ✅ | fuzzy |
| governing_law | grounded | Texas | Texas | ✅ | ✅ | exact |
| payment_terms | correct_refusal | None | — | ❌ | ❌ | — |
| confidentiality_clause | grounded | Receiving Party agrees to keep all Disclosing Part | Receiving Party agrees to keep all Disclosing Part | ✅ | ✅ | exact |

