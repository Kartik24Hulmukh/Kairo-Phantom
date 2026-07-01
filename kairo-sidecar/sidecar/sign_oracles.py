import os
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


def main():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    oracles_path = os.path.join(dir_path, "oracles.py")
    pub_path = os.path.join(dir_path, "oracles.py.pub")
    sig_path = os.path.join(dir_path, "oracles.py.sig")

    # Generate keypair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Save public key as PEM
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(pub_path, "wb") as f:
        f.write(pub_bytes)
    print(f"Public key saved to {pub_path}")

    # Sign the contents of oracles.py
    with open(oracles_path, "rb") as f:
        data = f.read()

    signature = private_key.sign(data)
    with open(sig_path, "wb") as f:
        f.write(signature)
    print(f"Signature saved to {sig_path}")


if __name__ == "__main__":
    main()
