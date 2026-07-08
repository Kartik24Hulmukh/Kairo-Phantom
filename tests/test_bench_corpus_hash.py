"""
Test: bench corpus hash is printed and deterministic for the same corpus.

This test is failing-capable: if the corpus hash changes between runs
on the same corpus, or is not printed, the test goes RED.
"""
import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _run_bench_capture_stdout() -> str:
    """Run the bench harness and return stdout."""
    output_path = REPO_ROOT / "bench" / "REPORT.json"
    result = subprocess.run(
        [sys.executable, "-m", "bench.harness", "--output", str(output_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    return result.stdout


def _run_bench_load_json() -> dict:
    """Run the bench harness and load the JSON output."""
    output_path = REPO_ROOT / "bench" / "REPORT.json"
    subprocess.run(
        [sys.executable, "-m", "bench.harness", "--output", str(output_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    with open(output_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_corpus_hash_printed_in_stdout():
    """The corpus hash must be printed in the bench stdout header."""
    stdout = _run_bench_capture_stdout()
    assert "Corpus Hash:" in stdout, "stdout missing 'Corpus Hash:' header"
    # The hash should be a 64-char hex string (SHA-256)
    import re
    match = re.search(r"Corpus Hash:\s+([0-9a-f]{64})", stdout)
    assert match, (
        f"Could not find a 64-char hex corpus hash in stdout. "
        f"Relevant lines:\n"
        + "\n".join(l for l in stdout.splitlines() if "Hash" in l)
    )


def test_corpus_hash_in_json_output():
    """The corpus hash must be present in the JSON output."""
    results = _run_bench_load_json()
    assert "corpus_hash" in results, "JSON output missing 'corpus_hash' field"
    corpus_hash = results["corpus_hash"]
    assert isinstance(corpus_hash, str), f"corpus_hash is {type(corpus_hash)}, expected str"
    assert len(corpus_hash) == 64, (
        f"corpus_hash length is {len(corpus_hash)}, expected 64 (SHA-256)"
    )
    # Must be valid hex
    int(corpus_hash, 16)  # Raises ValueError if not hex


def test_corpus_hash_deterministic_same_corpus():
    """Running bench twice on the same corpus must yield the same corpus hash."""
    results1 = _run_bench_load_json()
    hash1 = results1["corpus_hash"]
    results2 = _run_bench_load_json()
    hash2 = results2["corpus_hash"]
    assert hash1 == hash2, (
        f"Corpus hash changed between runs on the same corpus!\n"
        f"Run 1: {hash1}\n"
        f"Run 2: {hash2}"
    )


def test_corpus_hash_changes_when_corpus_changes(tmp_path):
    """The corpus hash must change when the corpus content changes.

    This verifies the hash is real, not hardcoded.
    """
    from bench.harness import compute_corpus_hash

    # Original corpus
    original_config = [
        {"name": "generic", "class": None, "dir": "fixtures/generic"},
        {"name": "invoice", "class": None, "dir": "fixtures/invoice"},
        {"name": "paper", "class": None, "dir": "fixtures/paper"},
        {"name": "contract", "class": None, "dir": "fixtures/contract"},
    ]
    hash_original = compute_corpus_hash(original_config)

    # Modified corpus: only one pack
    modified_config = [
        {"name": "generic", "class": None, "dir": "fixtures/generic"},
    ]
    hash_modified = compute_corpus_hash(modified_config)

    assert hash_original != hash_modified, (
        "Corpus hash did not change when corpus content changed — hash may be hardcoded!"
    )


def test_corpus_hash_is_sha256():
    """The corpus hash must be a valid SHA-256 hash (64 hex chars)."""
    results = _run_bench_load_json()
    corpus_hash = results["corpus_hash"]
    assert len(corpus_hash) == 64
    # Verify it's valid hexadecimal
    try:
        int(corpus_hash, 16)
    except ValueError:
        pytest.fail(f"corpus_hash is not valid hexadecimal: {corpus_hash}")


def test_model_id_pinned_in_output():
    """The model ID must be pinned and present in the output for reproducibility."""
    results = _run_bench_load_json()
    assert "model_id" in results, "JSON output missing 'model_id' field"
    assert isinstance(results["model_id"], str)
    assert len(results["model_id"]) > 0, "model_id is empty"
    # Model ID should be deterministic (not a random UUID)
    stdout = _run_bench_capture_stdout()
    assert "Model ID:" in stdout, "stdout missing 'Model ID:' header"


def test_seed_pinned_in_output():
    """The seed must be pinned and present in the output for reproducibility."""
    results = _run_bench_load_json()
    assert "seed" in results, "JSON output missing 'seed' field"
    assert isinstance(results["seed"], int)