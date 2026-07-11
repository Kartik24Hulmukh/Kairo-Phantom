# Fixtures & self-test

This folder is intentionally light. The loop's integrity is demonstrated by a
runnable self-test, not by committing synthetic "evidence" that could be
mistaken for the real thing.

## Prove the loop refuses fake green

```bash
cd loop-engineering
python3 tools/selftest_loop.py
```

It builds a throwaway environment in a temp dir (never touches the real
`state.json`), generates a demo Ed25519 key, and asserts:

1. an empty `{}` manifest is **rejected**
2. an unsigned manifest is **rejected**
3. a manifest signed by an **untrusted** key is **rejected**
4. a genuine signed manifest + a valid 100-run report is **accepted**
5. a report with readback 98/100 is **rejected** (computed from run records)
6. a manually altered history event is **detected** and mutation is **refused**

Exit code `0` means every integrity property holds. This is the "clone it,
run the verifier, tamper with it, observe the correct failure" check an
outside reviewer should be able to perform without you.

## Real evidence lives outside the repo

Real run reports, assessor statements, and signed manifests are produced during
the sprint and referenced by hash. Private signing keys never enter the repo
(see `tools/keygen.py`). Register only public keys in
`schemas/trust_roots.json`.
