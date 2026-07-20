# Releasing

## Large data files

The following files are not committed to the repository and ship as
release assets instead:

- `training_data/*.jsonl` — training datasets (large JSONL files)
- `phantom-core/target/imports/` — Rust target import caches

### Vendored models (do NOT remove)

`models/` contains vendored offline models that are intentionally
committed for offline-first operation. These must not be removed.

## Release asset process

1. Build training data: `python scripts/generate_dataset.py`
2. Build Rust components: `cargo build --release` (produces `phantom-core/target/`)
3. Package release assets alongside the repo archive
4. Upload to GitHub Releases as attached artifacts
