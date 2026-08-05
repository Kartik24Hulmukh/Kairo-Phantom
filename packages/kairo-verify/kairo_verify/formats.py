"""Format detection and the honest supported/planned list."""

SUPPORTED = [
    "kairo-receipts-jsonl (seq/prev_hash/self_hash/signature, canonical field order)",
    "kairo-checkpoints-jsonl (checkpoint_seq/tree_size/merkle_root, RFC 6962)",
]

PLANNED = [
    "Nobulex admission/outcome receipts (JCS / RFC 8785)",
    "asqav compliance receipts (ML-DSA-65 / FIPS 204)",
    "Obsigna W3C Verifiable Credentials",
    "Pipelock action receipts",
    "SCITT COSE_Sign1 signed statements",
]


def detect(record):
    if not isinstance(record, dict):
        return "unknown"
    if "checkpoint_seq" in record and "merkle_root" in record:
        return "kairo-checkpoint"
    if "seq" in record and "prev_hash" in record and "self_hash" in record:
        return "kairo-receipt"
    return "unknown"
