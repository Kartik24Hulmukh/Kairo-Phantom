#!/usr/bin/env python3
"""Sign an evidence manifest in place with an Ed25519 key from tools/keygen.py.

  python3 tools/sign_manifest.py --key ~/.kairo/kartik.key --manifest evidence/t3.json

The signature covers the canonical JSON of the manifest with the 'signature'
field removed — the same bytes validators.verify_signature() checks. Re-sign
after ANY edit to the manifest.
"""
import argparse, base64, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # import sibling validators.py
import validators as V
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--manifest", required=True)
    a = ap.parse_args()
    with open(a.key) as f:
        keyobj = json.load(f)
    sk = Ed25519PrivateKey.from_private_bytes(base64.b64decode(keyobj["private_b64"]))
    with open(a.manifest) as f:
        manifest = json.load(f)
    manifest["signer"] = keyobj["signer"]
    body = {k: v for k, v in manifest.items() if k != "signature"}
    sig = sk.sign(V.canonical(body))
    manifest["signature"] = base64.b64encode(sig).decode()
    with open(a.manifest, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"signed {a.manifest} as '{keyobj['signer']}'")


if __name__ == "__main__":
    main()
