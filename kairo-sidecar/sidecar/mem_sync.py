"""
kairo-sidecar/sidecar/mem_sync.py

Federated learning synchronization (FedAvg) with Differential Privacy (DP)
for style profile centroids. Logs privacy budgets to a SHA-256 audit chain.
"""

from __future__ import annotations
import math
import struct
import secrets
import hashlib
import sqlite3
import time
from typing import List


def clip_vector(vector: List[float], max_norm: float) -> List[float]:
    """Clips the vector to have L2 norm at most max_norm."""
    squared_sum = sum(x * x for x in vector)
    norm = math.sqrt(squared_sum)
    if norm <= max_norm or norm == 0:
        return vector

    scale = max_norm / norm
    return [x * scale for x in vector]


def _csprng_gauss(std_dev: float) -> float:
    """Box-Muller transform using OS entropy (CSPRNG-backed DP noise)."""
    while True:
        u1 = (struct.unpack("Q", secrets.token_bytes(8))[0] + 1) / (2**64 + 1)
        u2 = struct.unpack("Q", secrets.token_bytes(8))[0] / 2**64
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        return z * std_dev


def add_gaussian_noise(vector: List[float], std_dev: float) -> List[float]:
    """Adds zero-mean Gaussian noise with std_dev (CSPRNG-backed) to each coordinate."""
    return [x + _csprng_gauss(std_dev) for x in vector]


def compute_dp_delta(
    local_centroid: List[float],
    global_centroid: List[float],
    clipping_bound: float = 1.0,
    epsilon: float = 1.0,
    delta_dp: float = 1e-5,
) -> List[float]:
    """
    Computes the DP-noised difference: delta = clip(local - global, C) + N(0, sigma^2 * C^2).

    This guarantees (epsilon, delta)-DP for the client's local updates.
    There is no raw-text egress, only differentially private style vector deltas.
    """
    # 1. Calculate delta
    diff = [l - g for l, g in zip(local_centroid, global_centroid)]

    # 2. Clip L2 norm
    clipped_diff = clip_vector(diff, clipping_bound)

    # 3. Calculate Gaussian noise standard deviation
    # For Gaussian Mechanism, standard DP noise scale is:
    # sigma = sqrt(2 * ln(1.25/delta)) / epsilon
    sigma = math.sqrt(2.0 * math.log(1.25 / delta_dp)) / epsilon

    # Standard deviation for each coordinate is sigma * clipping_bound
    noise_std = sigma * clipping_bound

    # 4. Add noise
    dp_delta = add_gaussian_noise(clipped_diff, noise_std)

    return dp_delta


def federated_averaging(
    client_deltas: List[List[float]], global_centroid: List[float]
) -> List[float]:
    """
    Standard FedAvg aggregation step: global_centroid = global_centroid + mean(client_deltas).
    """
    if not client_deltas:
        return global_centroid

    num_clients = len(client_deltas)
    dim = len(global_centroid)

    sum_delta = [0.0] * dim
    for delta in client_deltas:
        for idx in range(min(dim, len(delta))):
            sum_delta[idx] += delta[idx]

    mean_delta = [d / num_clients for d in sum_delta]
    new_global = [g + md for g, md in zip(global_centroid, mean_delta)]

    return new_global


def log_privacy_budget_to_audit_chain(
    db_path: str, epsilon: float, delta: float, entry_type: str = "fed_sync"
) -> str:
    """
    Logs privacy budget allocations (epsilon, delta) to a SHA-256 audit chain
    stored in the database.

    Returns:
        The SHA-256 chain hash of the new audit record.
    """
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.row_factory = sqlite3.Row

        # Ensure audit_chain table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL,
                epsilon REAL NOT NULL,
                delta REAL NOT NULL,
                chain_hash TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        conn.commit()

        # Get the last chain hash
        row = conn.execute("SELECT chain_hash FROM audit_chain ORDER BY id DESC LIMIT 1").fetchone()

        prev_hash = row["chain_hash"] if row else "genesis_block_hash_000000000000000000000000000"

        # Calculate the new block hash
        timestamp = time.time()
        payload = f"{prev_hash}:{entry_type}:{epsilon}:{delta}:{timestamp}"
        new_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        # Insert new entry
        conn.execute(
            """
            INSERT INTO audit_chain (entry_type, epsilon, delta, chain_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry_type, epsilon, delta, new_hash, timestamp),
        )
        conn.commit()
        return new_hash
    finally:
        conn.close()
