# Kairo Phantom — Replication Report

> Generated: 2026-07-07T16:27:19.871609+00:00
> Corpus hash: `2e008813b3866e7d...`
> Platform: Linux-5.10.174-x86_64-with-glibc2.34
> Python: 3.13.11

## Aggregate Gates

| Gate | Measured | Target | Status |
| :--- | :--- | :--- | :--- |
| grounded_answer_rate | 96.39 | 95.0 | ✅ |
| false_refusal_rate | 3.61 | 5.0 | ❌ |
| refusal_on_unanswerable | 100.0 | 100.0 | ✅ |
| ungrounded_render_count | 0 | 0 | ✅ |

## Per-Pack Results

### generic

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 75.0% | ≥95% |
| False-Refusal Rate | 25.0% | <5% |
| Refusal-Correctness | 100.0% | 100% |
| Ungrounded Renders | 0 | 0 |

| Fixture | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- |
| sample_generic_01 | 4 | 3 | 1 | 25.0% |
| sample_generic_02 | 4 | 3 | 1 | 25.0% |
| sample_generic_03 | 4 | 3 | 1 | 25.0% |

### invoice

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 100.0% | ≥95% |
| False-Refusal Rate | 0.0% | <5% |
| Refusal-Correctness | 100.0% | 100% |
| Ungrounded Renders | 0 | 0 |

| Fixture | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- |
| sample_invoice_01 | 9 | 9 | 0 | 0.0% |
| sample_invoice_02 | 9 | 9 | 0 | 0.0% |
| sample_invoice_03 | 9 | 9 | 0 | 0.0% |

### paper

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 100.0% | ≥95% |
| False-Refusal Rate | 0.0% | <5% |
| Refusal-Correctness | 100.0% | 100% |
| Ungrounded Renders | 0 | 0 |

| Fixture | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- |
| sample_paper_01 | 8 | 8 | 0 | 0.0% |
| sample_paper_02 | 8 | 8 | 0 | 0.0% |
| sample_paper_03 | 8 | 8 | 0 | 0.0% |

### contract

| Metric | Value | Target |
| :--- | :--- | :--- |
| Grounded-Answer Rate | 100.0% | ≥95% |
| False-Refusal Rate | 0.0% | <5% |
| Refusal-Correctness | 100.0% | 100% |
| Ungrounded Renders | 0 | 0 |

| Fixture | Answerable | Grounded | False Refusals | FR Rate |
| :--- | :--- | :--- | :--- | :--- |
| sample_contract_01 | 7 | 7 | 0 | 0.0% |
| sample_contract_02 | 7 | 7 | 0 | 0.0% |
| sample_contract_03 | 6 | 6 | 0 | 0.0% |

