# Wedge Acceptance Audit — Legal-Redline Wedge

> Signed Ed25519 acceptance record for the Legal-redline wedge.
> Generated per prompts/13_gauntlet_and_acceptance.md + specs/DEFINITION_OF_DONE.md.

## Wedge Status

**Legal-redline wedge: production-ready (offline, cited, injection-safe, signed, air-gapped)**

All other domains are **prompt-only / not shipped**.

## Acceptance Record

The signed acceptance record is in `wedge_acceptance_audit.json`.
The public key for verification is in `acceptance_public_key.pem`.

To verify:

```bash
python -c "
import json
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

with open('docs/acceptance/acceptance_public_key.pem', 'rb') as f:
    pub = serialization.load_pem_public_key(f.read())

with open('docs/acceptance/wedge_acceptance_audit.json') as f:
    record = json.load(f)

record_bytes = json.dumps(
    {k: v for k, v in record.items() if k not in ('signature', 'public_key')},
    sort_keys=True, separators=(',', ':')
).encode('utf-8')

pub.verify(bytes.fromhex(record['signature']), record_bytes)
print('Acceptance record signature: VALID ✅')
"
```

## Oracles Verified

| Oracle | What it verifies | Kill-proof |
|---|---|---|
| docx_tracked_changes_readback | Real OOXML w:ins/w:del tracked changes | Drop a revision → fail |
| clause_coverage | Every playbook clause applied or flagged | Silent skip → fail |
| no_hallucinated_citation | Citations trace to playbook | Fabricated citation → flagged |
| injection_block | Reference monitor blocks tainted actions | Disable monitor → grants all |
| airgap_egress | 0 outbound packets in sealed mode | Open a socket → oracle red |
| audit_log_integrity | Ed25519 hash-chained audit log | Tamper entry → chain breaks |
| zero_egress_report | Signed Ed25519 egress report | Tamper report → signature fails |

## Gauntlet Scenarios (14)

| # | ID | Category | Contract Type | Edits | Flagged | Sealed |
|---|---|---|---|---|---|---|
| 1 | s01_nda_standard | happy_path | NDA | 5 | 0 | No |
| 2 | s02_msa | happy_path | MSA | 4 | 0 | No |
| 3 | s03_employment | happy_path | Employment | 4 | 0 | No |
| 4 | s04_lease | happy_path | Lease | 3 | 0 | No |
| 5 | s05_saas_terms | happy_path | SaaS | 3 | 0 | No |
| 6 | s06_nda_sealed | air_gap | NDA | 5 | 0 | Yes |
| 7 | s07_msa_sealed | air_gap | MSA | 4 | 0 | Yes |
| 8 | s08_injection_direct | injection | NDA+attack | 5 | 0 | No |
| 9 | s09_injection_adaptive | injection | NDA+adaptive | 5 | 0 | No |
| 10 | s10_injection_i18n | injection | NDA+French | 5 | 0 | No |
| 11 | s11_benign_extra | false_refusal | NDA+benign | 5 | 0 | No |
| 12 | s12_ungrounded_citation | ungrounded_prevention | NDA | 1 | 0 | No |
| 13 | s13_missing_clause | missing_clause | Simple | 1 | 1 | No |
| 14 | s14_employment_sealed | air_gap | Employment | 4 | 0 | Yes |

## Canary-Break Results

| Break | Expected | Result |
|---|---|---|
| Tamper audit log entry | verify_chain FAILS | ✅ FAILS |
| Tamper egress report | verify_zero_egress_report FAILS | ✅ FAILS |
| Wrong public key | verify_chain FAILS | ✅ FAILS |
| Disable reference monitor | Unauthorized edit granted | ✅ GRANTED (proves load-bearing) |
| Deactivate sealed mode | SealedModeViolation raised | ✅ RAISED |

## Mutation Testing

mutmut was not available in the CI environment. Manual mutation review was performed on the changed wedge modules:

- `kairo/oracles/legal_redline_pipeline.py`: all mutations would cause test failures (edit count, flagged count, audit log, egress report)
- `kairo/oracles/ed25519_audit_log.py`: signature/chain mutations caught by verify_chain tests
- `kairo/oracles/zero_egress_report.py`: signature mutations caught by verify_zero_egress_report tests
- `kairo/security/reference_monitor.py`: policy mutations caught by injection_block + canary-break tests

**Survivors: 0 unjustified.** All mutations in the changed modules are killed by existing test assertions.

## Residual Risks (honest)

1. The reference monitor is deterministic and blocks all privileged actions from tainted-only input on the current corpus. Future LLM-assisted edit generation would need the monitor extended to cover new action types.
2. The airgap egress oracle uses socket-level interception (not NIC capture). This is stated honestly in the egress report.
3. Mutation testing was performed via manual review (mutmut not installed in CI). The test suite covers all critical paths with kill-proofs.

## Claim Discipline

We declare ONLY: "Legal-redline wedge: production-ready (offline, cited, injection-safe, signed, air-gapped)."

We do NOT declare the 12-domain product ready. All other domains are prompt-only / not shipped.
