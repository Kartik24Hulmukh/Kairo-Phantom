# Kairo Phantom — Pack-Specific Benchmark Report

> Generated: 2026-07-08T11:21:04.662024+00:00

## Pack: `invoice`

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 100.0% | ≥95% |
| False-Refusal Rate | 0.0% | <5% |
| Refusal-Correctness | 100.0% | 100% |
| Ungrounded Renders | 0 | 0 |

### Hard Cases (invoice)

| Case | Answerable | Grounded | False Refusals | False-Refusal Rate |
| :--- | :--- | :--- | :--- | :--- |
| merged_cells | 9 | 9 | 0 | 0.0% |
| partially_scanned | 18 | 18 | 0 | 0.0% |

### Per-Document (invoice)

| Fixture | Source | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| sample_invoice_01 | base | 9 | 9 | 0 | 0.0% |
| sample_invoice_02 | base | 9 | 9 | 0 | 0.0% |
| sample_invoice_03 | base | 9 | 9 | 0 | 0.0% |
| sample_invoice_merged_01 | merged_cells | 9 | 9 | 0 | 0.0% |
| sample_invoice_partial_01 | partially_scanned | 9 | 9 | 0 | 0.0% |
| sample_invoice_partial_02 | partially_scanned | 9 | 9 | 0 | 0.0% |

## Pack: `contract`

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 100.0% | ≥95% |
| False-Refusal Rate | 0.0% | <5% |
| Refusal-Correctness | 27.27% | 100% |
| Ungrounded Renders | 8 | 0 |

### Hard Cases (contract)

| Case | Answerable | Grounded | False Refusals | False-Refusal Rate |
| :--- | :--- | :--- | :--- | :--- |
| cross_refs | 4 | 4 | 0 | 0.0% |

### Per-Document (contract)

| Fixture | Source | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| sample_contract_01 | base | 7 | 7 | 0 | 0.0% |
| sample_contract_02 | base | 7 | 7 | 0 | 0.0% |
| sample_contract_03 | base | 6 | 6 | 0 | 0.0% |
| sample_contract_xref_01 | cross_refs | 3 | 3 | 0 | 0.0% |
| sample_contract_xref_02 | cross_refs | 1 | 1 | 0 | 0.0% |

## Pack: `paper`

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 100.0% | ≥95% |
| False-Refusal Rate | 0.0% | <5% |
| Refusal-Correctness | 0.0% | 100% |
| Ungrounded Renders | 12 | 0 |

### Hard Cases (paper)

| Case | Answerable | Grounded | False Refusals | False-Refusal Rate |
| :--- | :--- | :--- | :--- | :--- |
| figure_captions | 4 | 4 | 0 | 0.0% |

### Per-Document (paper)

| Fixture | Source | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| sample_paper_01 | base | 8 | 8 | 0 | 0.0% |
| sample_paper_02 | base | 8 | 8 | 0 | 0.0% |
| sample_paper_03 | base | 8 | 8 | 0 | 0.0% |
| sample_paper_figcap_01 | figure_captions | 2 | 2 | 0 | 0.0% |
| sample_paper_figcap_02 | figure_captions | 2 | 2 | 0 | 0.0% |

## Pack: `generic`

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 75.0% | ≥95% |
| False-Refusal Rate | 25.0% | <5% |
| Refusal-Correctness | 100.0% | 100% |
| Ungrounded Renders | 0 | 0 |

### Per-Document (generic)

| Fixture | Source | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| sample_generic_01 | base | 4 | 3 | 1 | 25.0% |
| sample_generic_02 | base | 4 | 3 | 1 | 25.0% |
| sample_generic_03 | base | 4 | 3 | 1 | 25.0% |

