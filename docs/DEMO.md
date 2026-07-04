# Kairo Phantom — Legal Redline Demo

> A human-runnable demo of the offline Legal-redline wedge: real tracked changes,
> Ed25519-signed audit log, signed zero-egress report, and (optionally) live
> air-gap egress capture. **No network. No LLM. No cloud.**

## Prerequisites

```bash
pip install python-docx cryptography
```

## Quick Start (3 commands)

### 1. Redline the demo NDA

```bash
python -m kairo.cli redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --out demo_output
```

This runs the REAL pipeline on the demo NDA and writes:
- `demo_output/redlined.docx` — the contract with real OOXML tracked changes (`w:ins`/`w:del`)
- `demo_output/audit_log.json` — Ed25519-signed, hash-chained audit log
- `demo_output/zero_egress_report.json` — signed report attesting zero network egress
- `demo_output/public_key.pem` — public key for independent verification
- `demo_output/.keys/private_key.pem` — private key (generated locally, never committed)

### 2. Redline in sealed mode (air-gap egress capture)

```bash
python -m kairo.cli redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --sealed --out demo_sealed
```

Same as above, but additionally:
- Activates sealed mode (one-way switch, no cloud fallback path)
- Installs socket-level egress interception (blocks + records all outbound connections)
- Writes `demo_sealed/airgap_egress_report.json` — deterministic report showing 0 outbound packets
- Prints "Air-gap: 0 outbound packets ✅"

### 3. Independently verify the artifacts

```bash
python -m kairo.cli verify demo_output demo_output/public_key.pem
```

This re-verifies **without trusting us**:
- Audit log: every Ed25519 signature + hash-chain linkage
- Zero-egress report: Ed25519 signature
- Redlined document: exists and is non-empty
- Air-gap report (if present): 0 egress + 0 DNS + flow completed

Prints PASS/FAIL per artifact and an overall verdict.

## Sample Output

```
============================================================
  KAIRO PHANTOM — LEGAL REDLINE COMPLETE
============================================================
  Contract:    sample_nda.docx
  Playbook:    nda_playbook.json
  Output:      /path/to/demo_output
  Edits applied:  5
  Clauses flagged: 0
  Injection detected: False

  Applied edits:
    • Governing Law: laws of the State of Delaware... → laws of the State of California...
    • Limitation of Liability: Liability is unlimited for all claims... → Each Party's aggregate liability...
    • Termination Notice Period: 90 days notice... → 30 days prior written notice...
    • Confidentiality Survival: survive termination of this Agreement for five years... → survive termination of this Agreement for three (3) years...
    • Indemnification Cap: The indemnifying Party's total liability... → The indemnifying Party's total liability shall not exceed...

  Audit log verified: ✅
  Zero-egress report verified: ✅

  Artifacts in /path/to/demo_output/:
    redlined.docx
    audit_log.json
    zero_egress_report.json
    public_key.pem
============================================================
```

## What Each Output Means

| Artifact | What it is | How to verify |
|---|---|---|
| `redlined.docx` | The NDA with real Word tracked changes (insertions/deletions) | Open in Microsoft Word → Review → Track Changes |
| `audit_log.json` | Tamper-evident, hash-chained, Ed25519-signed log of every edit | `python -m kairo.cli verify <dir> <public_key.pem>` |
| `zero_egress_report.json` | Signed report attesting the run had zero network egress | Same verify command; signature is Ed25519-verifiable |
| `public_key.pem` | Ed25519 public key for verifying the above signatures | Share with any skeptic; they can verify independently |
| `airgap_egress_report.json` | (Sealed mode only) Deterministic report from live socket interception | Check `total_egress_attempts: 0` and `total_dns_lookups: 0` |

## Claim Discipline

Per `specs/CLAIM_DISCIPLINE.md`:

- ✅ "Runs fully on your device. Every run emits a reproducible, signed egress report
  showing zero outbound connections, verifiable by your own network monitor."
- ❌ NOT "cryptographic proof no bytes ever leave." The report proves zero egress
  *during an observed run* — reproducibility + auditability, not an impossibility proof.

## Kill-Proof: Tamper Detection

To verify the audit log is tamper-evident:

```bash
# Run the redline
python -m kairo.cli redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --out demo_output

# Verify (should PASS)
python -m kairo.cli verify demo_output demo_output/public_key.pem

# Tamper with the audit log
python -c "import json; d=json.load(open('demo_output/audit_log.json')); d['entries'][0]['action']='tampered'; json.dump(d, open('demo_output/audit_log.json','w'), indent=2)"

# Verify again (should FAIL)
python -m kairo.cli verify demo_output demo_output/public_key.pem
```

The second verify will print `FAIL ❌` because the Ed25519 signature no longer matches.
