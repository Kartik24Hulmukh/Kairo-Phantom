import os
import sys
import time
import sqlite3
import tempfile
import shutil
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.mem_machine import MemMachineClient


@pytest.fixture
def temp_db():
    """Create a temporary DB path for each test."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memmachine.db")
    yield db_path
    shutil.rmtree(temp_dir)


def test_db_created_on_init(temp_db):
    MemMachineClient(db_path=temp_db)
    assert os.path.exists(temp_db)


def test_record_and_query(temp_db):
    client = MemMachineClient(db_path=temp_db)
    client.record_interaction(
        domain="word",
        task_type="insert",
        user_prompt="write a memo",
        output_preview="Here is the memo: ...",
        confidence=0.95,
        style_notes="User prefers bullet points",
    )
    result = client.query(domain="word")
    assert "word" in result.lower() or "insert" in result or "bullet" in result


def test_query_empty_returns_empty_string(temp_db):
    client = MemMachineClient(db_path=temp_db)
    result = client.query(domain="nonexistent_domain")
    assert result == ""


def test_record_multiple_interactions(temp_db):
    client = MemMachineClient(db_path=temp_db)
    for i in range(10):
        client.record_interaction(
            domain="excel",
            task_type="formula",
            user_prompt=f"write formula {i}",
            output_preview=f"=SUM(A{i}:B{i})",
            confidence=0.9,
        )
    result = client.query(domain="excel", limit=5)
    assert result  # Not empty
    assert "excel" in result.lower() or "formula" in result.lower()


def test_style_profile(temp_db):
    client = MemMachineClient(db_path=temp_db)
    client.record_interaction(domain="word", task_type="insert", user_prompt="p1", confidence=0.95)
    client.record_interaction(domain="word", task_type="insert", user_prompt="p2", confidence=0.9)
    client.record_interaction(domain="word", task_type="replace", user_prompt="p3", confidence=0.85)

    profile = client.get_style_profile(domain="word")
    assert profile["domain"] == "word"
    task_types = [t["task_type"] for t in profile["task_frequencies"]]
    assert "insert" in task_types
    insert_count = next(
        t["count"] for t in profile["task_frequencies"] if t["task_type"] == "insert"
    )
    assert insert_count == 2


def test_clear_domain_history(temp_db):
    client = MemMachineClient(db_path=temp_db)
    client.record_interaction(domain="word", task_type="insert", user_prompt="test")
    client.record_interaction(domain="word", task_type="replace", user_prompt="test2")
    deleted = client.clear_domain_history(domain="word")
    assert deleted == 2
    result = client.query(domain="word")
    assert result == ""


def test_query_latency_under_300ms(temp_db):
    client = MemMachineClient(db_path=temp_db)
    # Insert 100 interactions
    for i in range(100):
        client.record_interaction(
            domain="word", task_type="insert", user_prompt=f"prompt {i}", confidence=0.9
        )

    start = time.time()
    client.query(domain="word", limit=5)
    elapsed_ms = (time.time() - start) * 1000
    assert elapsed_ms < 300  # Sub-300ms recall (roadmap spec)


def test_isolation_between_domains(temp_db):
    client = MemMachineClient(db_path=temp_db)
    client.record_interaction(
        domain="word", task_type="insert", user_prompt="word stuff", style_notes="Use bullets"
    )
    client.record_interaction(
        domain="excel", task_type="formula", user_prompt="excel stuff", style_notes="Use formulas"
    )

    word_result = client.query(domain="word")
    excel_result = client.query(domain="excel")

    assert "bullets" in word_result.lower() or "word" in word_result.lower()
    assert "formula" in excel_result.lower() or "excel" in excel_result.lower()
    # Cross-contamination check
    assert "formula" not in word_result.lower() or "word" in word_result.lower()


def test_record_returns_true_on_success(temp_db):
    client = MemMachineClient(db_path=temp_db)
    result = client.record_interaction(
        domain="code", task_type="insert", user_prompt="add docstring"
    )
    assert result is True


def test_record_long_prompt_truncated(temp_db):
    client = MemMachineClient(db_path=temp_db)
    long_prompt = "x" * 1000  # 1000 chars
    result = client.record_interaction(domain="word", task_type="insert", user_prompt=long_prompt)
    assert result is True
    # Verify it was truncated in DB
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT user_prompt FROM interactions LIMIT 1").fetchone()
    conn.close()
    assert len(row[0]) <= 500


def test_user_isolation(temp_db):
    client = MemMachineClient(db_path=temp_db)
    client.record_interaction(
        domain="word",
        task_type="insert",
        user_prompt="user1 memo",
        user_id="user1",
        style_notes="formal",
    )
    client.record_interaction(
        domain="word",
        task_type="insert",
        user_prompt="user2 memo",
        user_id="user2",
        style_notes="casual",
    )

    user1_result = client.query(user_id="user1", domain="word")
    user2_result = client.query(user_id="user2", domain="word")

    assert "formal" in user1_result
    assert "casual" in user2_result
    # Cross-contamination check
    assert "casual" not in user1_result
    assert "formal" not in user2_result


def test_style_vectors_and_centroids(temp_db):
    client = MemMachineClient(db_path=temp_db)

    # Check recording style vectors
    client.record_interaction(
        domain="word", task_type="insert", user_prompt="prompt 1", style_vector=[0.1, 0.2, 0.3]
    )
    client.record_interaction(
        domain="word", task_type="insert", user_prompt="prompt 2", style_vector=[0.3, 0.4, 0.5]
    )

    # Centroid should be the element-wise mean: [0.2, 0.3, 0.4]
    centroid = client.get_style_centroid(domain="word")
    assert centroid is not None
    assert len(centroid) == 3
    assert abs(centroid[0] - 0.2) < 1e-5
    assert abs(centroid[1] - 0.3) < 1e-5
    assert abs(centroid[2] - 0.4) < 1e-5


def test_federated_dp_sync(temp_db):
    from sidecar.mem_sync import (
        compute_dp_delta,
        federated_averaging,
        log_privacy_budget_to_audit_chain,
    )

    local_centroid = [0.2, 0.3, 0.4]
    global_centroid = [0.1, 0.1, 0.1]

    # Delta should be noised and clipped difference
    delta = compute_dp_delta(
        local_centroid, global_centroid, clipping_bound=1.0, epsilon=1.0, delta_dp=1e-5
    )
    assert len(delta) == 3

    # Test FedAvg
    client_deltas = [delta]
    new_global = federated_averaging(client_deltas, global_centroid)
    assert len(new_global) == 3

    # Test Privacy Budget Audit Chain
    hash1 = log_privacy_budget_to_audit_chain(temp_db, epsilon=0.5, delta=1e-6)
    hash2 = log_privacy_budget_to_audit_chain(temp_db, epsilon=0.5, delta=1e-6)

    assert hash1 != hash2
    assert len(hash1) == 64
    assert len(hash2) == 64
