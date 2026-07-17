# Legal v3 — Technical-Preview Runbook

## Prerequisites

```bash
pip install cryptography python-docx
export PYTHONPATH=.
```

## Full CLI flow

```bash
# 1. Generate separate identities
python3 tools/kairo_legal_v3.py keygen producer work/producer.json
python3 tools/kairo_legal_v3.py keygen approver work/approver.json
python3 tools/kairo_legal_v3.py keygen observer work/observer.json

# 2. Propose a redline
python3 tools/kairo_legal_v3.py propose \
  work nda.docx playbook.json out.docx \
  work/producer.json work/proposal.json

# 3. Approve the proposal (human approval)
python3 tools/kairo_legal_v3.py approve \
  work/proposal.json work/approver.json work/approval.json

# 4. Execute the redline (producer + approver keys + independent observer)
python3 tools/kairo_legal_v3.py execute \
  work work/proposal.json work/approval.json \
  work/producer.json work/approver.json work/observer.json work/bundle

# 5. Verify the evidence bundle (offline, no keys needed)
python3 tools/kairo_legal_v3.py verify work/bundle
```

## Expected verifier output

```json
{
  "ok": true,
  "integrity": "pass",
  "execution": "pass",
  "sufficiency": "complete_for_declared_boundary",
  "domain": "requires_human_review"
}
```

A successful verifier result still reports `domain: requires_human_review`.
Cryptographic integrity does not equal legal acceptance.

## Running tests

```bash
# Focused test suite (24 tests)
PYTHONPATH=. python3 -m pytest tests/test_legal_v3_e2e.py \
  tests/test_legal_v3_adversarial.py \
  tests/test_legal_v3_negative_conformance.py -v

# 100-run synthetic soak
PYTHONPATH=. python3 scripts/legal_v3_soak.py --runs 100

# Release build + surface audit
PYTHONPATH=. python3 scripts/build_legal_v3_release.py target/legal-v3-release
```

## Release staging

```bash
PYTHONPATH=. python3 scripts/build_legal_v3_release.py target/legal-v3-release
```

Produces:
- `target/legal-v3-release/RELEASE_MANIFEST.json` — file list + SHA-256 digests
- `target/legal-v3-release/SURFACE_AUDIT.json` — zero-finding audit result

The staged release excludes all twelve legacy domains, desktop automation,
peer networking, and runtime package acquisition.
