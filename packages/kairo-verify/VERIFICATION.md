# Verification receipt - kairo-verify 0.1.0

Generated: 2026-08-05T12:57:46Z (UTC)
Environment: Python 3.13.13, cryptography 49.0.0, Linux sandbox

## Test suite (stdlib unittest, real Ed25519 keys + obsigna cross-SDK vector)

```
----------------------------------------------------------------------
Ran 26 tests in 0.312s

OK
```

## Obsigna format validation (against agent-receipts/obsigna cross-sdk-tests/py_vectors.json)

```
canonical matches their vector: True
hash matches their vector: True
their signed receipt verifies: True
tampered copy rejected: True
```

## Adversarial stress suite

```
PERF: 10,000 receipts verified in 1.23s, violations=0
FUZZ: 60/60 field mutations detected
EXTENSION FIELD: detected -> ["receipt[2] seq=2: unverified extension field(s) ['injected_unsigned_field'] (not covered by signature)"]
RESULT: passes=16 findings=0
```

## Findings from stress testing (fixed, with regression tests)

1. `seq` with a non-integer type crashed the verifier (TypeError) -> now reported as a violation (`seq is not an integer`).
2. Unknown extension fields were silently accepted (unsigned, unverified by design of fixed-order canonicalization) -> now flagged (`unverified extension field(s) ... (not covered by signature)`).

## What this does not prove

- It does not prove the main Kairo engine produces these receipts (that path is in the engine repo).
- Obsigna proof verification requires the issuer key out-of-band (--key); receipts reference keys by DID and offline DID resolution is impossible by design.
- Other foreign formats (Nobulex, asqav, Pipelock, SCITT) are planned, not implemented.
- It does not prove anything about legal admissibility.
