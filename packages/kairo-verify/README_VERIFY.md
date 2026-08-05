# kairo-verify

Offline verifier for AI agent execution receipts. One dependency (`cryptography`), no models, no network calls, no telemetry.

## What it verifies
**Kairo-Phantom receipts (jsonl):**
1. **Hash chain** — `prev_hash` continuity from `"genesis"`, seq monotonicity.
2. **Content integrity** — recomputes each receipt's canonical `self_hash` (fixed field order, compact JSON, `self_hash`/`signature` emptied). Never trusts stored hashes.
3. **Ed25519 signatures** — signature over the ASCII bytes of `self_hash`, with `agent_id` as the hex verifying key.
4. **Merkle checkpoints** — recomputes the RFC 6962 root over the receipts' *recomputed* content hashes; detects receipts truncated after a checkpoint.
5. **Envelope hygiene** — fields outside the canonical order are flagged as unverified extension fields (not covered by the signature).

**Obsigna Agent Receipts (W3C VC, `agent-receipts/obsigna`):**
- Structure and required fields per their spec.
- **Ed25519Signature2020 proofs** — signature over the RFC 8785 (JCS) canonical JSON of the receipt without proof; `proofValue` is multibase base64url. Scheme validated against their published cross-SDK test vectors (`cross-sdk-tests/py_vectors.json`).
- **Chain linkage** — `credentialSubject.chain.sequence` continuity and `previous_receipt_hash` matching the recomputed hash of the prior receipt.
- Keys are DID-referenced in receipts; offline DID resolution is impossible by design, so pass the verifying key with `--key <pem>` (out-of-band). Without it, structural and chain checks still run and the signature is reported UNVERIFIED.

## What it does NOT verify
- Whether the *content* of any action was correct, lawful, or intended.
- Legal admissibility of anything. Untested in any jurisdiction.
- JSON-LD context resolution (offline, no network). Verification is over the JCS canonical form exactly as the obsigna cross-SDK vectors define.
- Other foreign formats (Nobulex / asqav / Pipelock / SCITT) — planned. `kairo-verify formats` shows the honest list.

## The answerability report
`kairo-verify answer <receipts.jsonl>` states, for four determinations, either **ANSWERED** (with the receipt seqs carrying the answer) or **NOT ANSWERABLE FROM THIS RECORD** (with the missing typing or relation named):
- D1: Did protected data cross a boundary?
- D2: Could a human have intervened before the irreversible step?
- D3: Did the barrier hold, or was it merely present?
- D4: Was delegated authority valid at the moment it was used?

The recognizer is deliberately conservative: a false NOT ANSWERABLE is intended; a false ANSWERED is a bug. Integrity ≠ answerability.

## Usage
```
pip install .
kairo-verify demo --out /tmp/kvd
kairo-verify integrity /tmp/kvd/receipts.jsonl --checkpoints /tmp/kvd/checkpoints.jsonl
kairo-verify integrity obsigna_receipts.jsonl --key issuer_key.pem
kairo-verify answer /tmp/kvd/receipts.jsonl [--json]
kairo-verify formats [/path/to/file.jsonl]
```
Exit codes for `integrity`: 0 = all checks passed; 1 = violations found; 2 = usage error.

## Tests and stress results
See `VERIFICATION.md`: 26 stdlib-unittest tests (real Ed25519 keys, plus the obsigna cross-SDK signed vector) and an adversarial stress suite (60/60 fuzzed mutations detected, 10,000 receipts in ~1.5s, extension-field injection flagged, malformed `seq` reported not crashed).

## Status
Alpha. The Kairo receipt contract mirrors `tools/verify_receipts_external.py` in the Kairo-Phantom repo (field order from `phantom-core/src/identity.rs`), with two hardening additions found by stress testing. Key custody in the producing system is currently file-based — see `docs/OPEN_BLOCKERS.md` in that repo.
