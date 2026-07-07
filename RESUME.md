# RESUME — kairo-phantom-100x-execution checkpoint

Last updated: 2026-07-07. Branch: `kairo-phantom-100x-execution` (base: `master`).
Rules in force: NO-FAKE-GREEN — every green must be backed by evidence; degraded
fallbacks must be loud; stub-only coverage must be labeled Experimental.

## DONE (this session, with evidence)

### 1. Anti-fake-green hardening of the 4 earlier fixes
- `kairo/docintel/retrieval.py`: hash-embedding fallback is now LOUD
  (`logger.error` + "DEGRADED" wording), and `KAIRO_REQUIRE_SEMANTIC=1` makes a
  missing model2vec model a hard `RuntimeError` instead of a silent downgrade.
  Evidence: manual run with empty `HF_HOME` + `KAIRO_REQUIRE_SEMANTIC=1` raises;
  with model cached, backend == "model2vec".
- `tests/e2e/conftest.py` (new): sets `KAIRO_REQUIRE_SEMANTIC=1` for every e2e
  test (the e2e test file itself is FROZEN and could not be edited).
- `kairo-sidecar/sidecar/writers/writing_intelligence.py`:
  `process_and_sanitize` docstring now carries an explicit
  "EXPERIMENTAL — STUB-ONLY SANITIZATION" label: there is NO real paraphrase
  service; the only sanitization path is the `KAIRO_PARAPHRASE_STUB=1` stub;
  prod behavior (stub off) raises MemorizationError and is covered by
  `kairo-sidecar/tests/test_production_mocks_gating.py`.

### 2. Cargo release profile fixed (was fake-optimized)
- `Cargo.toml [profile.release]` was `opt-level=0, lto=false, strip=none`
  while the comment claimed "full optimization" — release builds were debug
  builds. Now: `opt-level=3, lto="thin", strip="symbols"`, with a comment
  documenting the history.

### 3. Trust-claim audit (item 4)
- grep audit over all non-blueprint *.md: NO doc claims Merkle log,
  policy-as-code, co-signing, deterministic replay, or transparency log exist.
  Zero relabels required. Agent identity claims (SPIFFE/Ed25519) are backed by
  real code (`phantom-core/src/identity.rs`,
  `phantom-core/src/enterprise/spiffe_identity.rs`).
- `kairo/trust/__init__.py` documents which trust-layer features are
  IMPLEMENTED vs PLANNED.

### 4. W7 trust layer started (oracle-first)
- `kairo/trust/merkle.py` (new): RFC 6962 Merkle tree over receipts'
  RECOMPUTED canonical hashes + Ed25519-signed, hash-chained checkpoints;
  inclusion proofs (`merkle_proof`/`verify_merkle_proof`).
- `tests/test_merkle_receipts.py` (new): 17 tests, all passing. Includes
  EXTERNAL ORACLE vectors from RFC 6962 / certificate-transparency-go
  (empty root `e3b0c442...`, d1/d2/d3 known-answer roots) — verified
  independently before implementation.
- `tools/verify_receipts_external.py` (new): STANDALONE verifier — zero repo
  imports, stdlib + optional `cryptography`. Verifies linear hash chain,
  recomputed content hashes, Ed25519 signatures, Merkle checkpoint roots,
  checkpoint chain, truncation/rollback.
- Adversarial evidence (all run against the real script as subprocess):
  CLEAN exit=0; EDIT-CONTENT exit=1 (self_hash mismatch + Merkle root
  mismatch); EDIT+REHASH-without-key exit=1 (invalid signature + chain break +
  Merkle mismatch); DELETE-RECEIPT exit=1 (truncation + seq gap);
  TRUNCATE exit=1 (tree_size exceeds receipt count).
- Honest limits (documented in merkle.py docstring): all signatures use the
  agent's OWN key. An attacker with disk write access AND the private key can
  rewrite everything. External witness/transparency publication is PLANNED,
  not implemented.

### 5. CI OOM fix
- `.github/workflows/root_suite.yml` (+ fallback copy at
  `ci/root_suite.yml.proposed` in case the Git App lacks `workflows`
  permission): 4-way file shard matrix + pytest-xdist (`--dist loadfile`),
  model2vec model cached via actions/cache and pre-downloaded on miss,
  `KAIRO_REQUIRE_SEMANTIC=1` in the run env. Root cause: single-process full
  suite accumulates memory (test_resource_bounds.py allocates deliberately)
  → exit 137 in 4 GB sandbox.

## NEXT STEPS (in order)
1. Commit + push branch; open PR against master. If push is rejected due to
   workflow permissions, delete `.github/workflows/root_suite.yml` from the
   commit, keep `ci/root_suite.yml.proposed`, and tell the maintainer to move
   it (one `git mv`).
2. Watch PR CI on the head commit (`gh run list/watch`). Do NOT declare done
   until green. Known risk: pre-existing workflows may have unrelated failures
   on master — compare against master's CI status before attributing to this
   branch.
3. W7 continuation: wire checkpoint creation into the sidecar receipt path
   (create_checkpoint on shutdown/interval), then external witness publication
   (currently PLANNED).
4. Remaining trust-layer gaps (policy-as-code, co-signing, deterministic
   replay) are still NOT implemented — do not let any doc claim otherwise.

## Environment recreation (sandbox)
- Python: venv at /tmp/kairo-venv; `pip install -r kairo-sidecar/requirements.txt -r requirements-test.txt pytest pytest-asyncio`.
- model2vec: `python -c "from model2vec import StaticModel; StaticModel.from_pretrained('minishlab/potion-base-8M')"`.
- Rust: rustup minimal + dnf: gcc gcc-c++ make pkgconfig openssl-devel glib2-devel
  atk-devel at-spi2-core-devel at-spi2-atk-devel libX11-devel libXtst-devel
  libxcb-devel libXi-devel dbus-devel libxdo-devel (gtk3/webkit for full workspace).
- Full suite in one process OOMs at 4 GB — run in chunks of ~8-10 files.
