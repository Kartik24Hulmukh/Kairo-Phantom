# kairo-verify

Offline verifier for Kairo-Phantom execution receipts. One dependency (`cryptography`), no models, no network calls, no telemetry.

## What it verifies
1. **Hash chain** — `prev_hash` continuity from `"genesis"`, seq monotonicity.
2. **Content integrity** — recomputes each receipt's canonical `self_hash` (fixed field order, compact JSON, `self_hash`/`signature` emptied) and compares against the stored value. Never trusts stored hashes.
3. **Ed25519 signatures** — signature over the ASCII bytes of `self_hash`, with `agent_id` as the hex verifying key.
4. **Merkle checkpoints** — recomputes the RFC 6962 root over the receipts' *recomputed* content hashes; detects receipts truncated after a checkpoint; verifies the checkpoint chain and signatures.
5. **Envelope hygiene** — any field outside the canonical order is flagged as an unverified extension field (it is not covered by the signature).

## What it does NOT verify
- Whether the *content* of any action was correct, lawful, or intended.
- Legal admissibility of anything. Untested in any jurisdiction.
- Foreign receipt formats (Nobulex / asqav / Obsigna / Pipelock / SCITT) — planned, not yet implemented. `kairo-verify formats` shows the honest list.

## The answerability report
`kairo-verify answer <receipts.jsonl>` states, for four determinations, either **ANSWERED** (with the receipt seqs carrying the answer) or **NOT ANSWERABLE FROM THIS RECORD** (with the missing typing or relation named):
- D1: Did protected data cross a boundary?
- D2: Could a human have intervened before the irreversible step?
- D3: Did the barrier hold, or was it merely present?
- D4: Was delegated authority valid at the moment it was used?

The recognizer is deliberately conservative: a false NOT ANSWERABLE is intended; a false ANSWERED is a bug. Integrity ≠ answerability — passing all integrity checks says nothing about whether the record can answer these questions.

## Usage
```
pip install .
kairo-verify demo --out /tmp/kvd            # plain receipts (also: --typed)
kairo-verify integrity /tmp/kvd/receipts.jsonl --checkpoints /tmp/kvd/checkpoints.jsonl
kairo-verify answer /tmp/kvd/receipts.jsonl [--json]
kairo-verify formats [/path/to/file.jsonl]
```
Exit codes for `integrity`: 0 = all checks passed; 1 = violations found; 2 = usage error.

## Tests and stress results
See `VERIFICATION.md` for the captured output: 15 stdlib-unittest tests (real Ed25519 keys) plus an adversarial stress suite (60/60 fuzzed mutations detected, 10,000 receipts verified in ~1.5s, extension-field injection flagged, malformed `seq` types reported rather than crashing).

## Status
Alpha. The receipt contract mirrors `tools/verify_receipts_external.py` in the Kairo-Phantom repo (canonical field order from `phantom-core/src/identity.rs`), with two hardening additions found by stress testing: non-integer `seq` values are violations rather than crashes, and out-of-contract extension fields are flagged as unsigned. Key custody in the producing system is currently file-based — see `docs/OPEN_BLOCKERS.md` in that repo.
