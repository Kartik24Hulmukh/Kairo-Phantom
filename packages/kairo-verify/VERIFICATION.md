# Verification receipt - kairo-verify 0.1.0

Generated: 2026-08-05T12:22:23Z (UTC)
Environment: Python 3.13.13, cryptography 49.0.0, Linux sandbox

## Test suite (stdlib unittest, real Ed25519 keys)

```
----------------------------------------------------------------------
Ran 15 tests in 0.261s

OK
```

## Adversarial stress suite

```
PERF: 10,000 receipts verified in 1.51s, violations=0
FUZZ: 60/60 field mutations detected
EXTENSION FIELD: detected -> ["receipt[2] seq=2: unverified extension field(s) ['injected_unsigned_field'] (not covered by signature)"]

RESULT: passes=16 findings=0
```

## Findings from stress testing (fixed, with regression tests)

1. `seq` with a non-integer type crashed the verifier (TypeError) -> now reported as a violation (`seq is not an integer`).
2. Unknown extension fields were silently accepted (unsigned, unverified by design of fixed-order canonicalization) -> now flagged (`unverified extension field(s) ... (not covered by signature)`).

## Round-trip: clean chain verifies

```
OK - all checks passed (5 receipts, 1 checkpoints: hash chain, content hashes, Ed25519 signatures, Merkle checkpoints)
exit=0
```

## Round-trip: one-byte tamper is detected

```
FAIL - 1 violation(s):
  - receipt[2] seq=2: self_hash mismatch (content was modified)
exit=1
```

## What this does not prove

- It does not prove the main Kairo engine produces these receipts (that path is in the engine repo).
- It does not prove foreign-format support (planned, see README_VERIFY.md).
- It does not prove anything about legal admissibility.
