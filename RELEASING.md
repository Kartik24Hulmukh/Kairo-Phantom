# Releasing

## Counterparty key distribution

The `kairo verify` command requires a trusted public key supplied
externally — it does NOT trust the `public_key.pem` co-located in the
output directory (an attacker can replace it).

### How a counterparty obtains the trusted key out-of-band

1. **In person:** The redline operator reads the public key fingerprint:
   ```bash
   sha256sum redline_output/public_key.pem
   ```
   and communicates it to the counterparty via a trusted channel
   (phone, in-person, signed email).

2. **Verify with external key:**
   ```bash
   kairo verify <output_dir> <trusted_key.pem>
   ```

3. **Verify with fingerprint:**
   ```bash
   kairo verify <output_dir> --fingerprint <sha256_hex>
   ```
   This checks the co-located `public_key.pem` against the expected
   fingerprint. If the key has been swapped, verification fails.

4. **Key rotation:** Generate a new keypair by deleting the `.keys/`
   directory in the output dir. The new public key fingerprint must be
   re-distributed to all counterparties.

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
