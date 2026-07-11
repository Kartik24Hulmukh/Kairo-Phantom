#!/usr/bin/env python3
"""Generate an Ed25519 signing key for evidence manifests.

  python3 tools/keygen.py --signer kartik-founder --out ~/.kairo/kartik.key

Writes the PRIVATE key (base64 raw seed) to --out (keep it OFF the repo) and
prints the PUBLIC key to register in schemas/trust_roots.json under --signer.
"""
import argparse, base64, json, os, sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signer", required=True)
    ap.add_argument("--out", required=True, help="path to write the private key (base64)")
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"refusing to overwrite existing key at {a.out}")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sk = Ed25519PrivateKey.generate()
    seed = sk.private_bytes_raw()
    pub = sk.public_key().public_bytes_raw()
    with open(a.out, "w") as f:
        json.dump({"signer": a.signer, "private_b64": base64.b64encode(seed).decode()}, f)
    os.chmod(a.out, 0o600)
    pub_b64 = base64.b64encode(pub).decode()
    print(f"private key written to {a.out} (mode 600 — keep it secret, keep it off the repo)")
    print("\nRegister this in schemas/trust_roots.json under \"signers\":")
    print(f'  "{a.signer}": "{pub_b64}"')


if __name__ == "__main__":
    main()
