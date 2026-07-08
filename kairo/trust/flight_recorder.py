"""
W7 Trust Layer — Deterministic Replay / Flight Recorder.

Records a complete execution trace (inputs, outputs, receipts, checkpoints)
in a deterministic, replayable format. Any recorded run can be re-verified
by replaying the trace and checking that the same receipts are produced.

The flight recorder is OFFLINE-FIRST: it uses local timestamps and
hash-chained entries. No network calls are made.

Design:
- Each run produces a FlightLog (JSONL file) with one entry per stage.
- Each entry is hash-chained to the previous entry (like receipts).
- The final entry contains the Merkle root of all receipt hashes.
- Replay: re-run the same inputs through the same code and verify
  that the same hash chain and Merkle root are produced.

Threat model: The flight recorder proves that a specific sequence of
operations produced specific outputs. Combined with the Merkle checkpoint,
this gives end-to-end verifiability without trusting the agent.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


__all__ = [
    "FlightEntry",
    "FlightLog",
    "record_flight",
    "replay_flight",
    "verify_flight_log",
]


@dataclass
class FlightEntry:
    """A single entry in the flight recorder log."""
    seq: int
    timestamp: int
    stage: str  # e.g. "ingest", "extract", "ground", "quality_gate"
    input_hash: str  # SHA-256 of canonical input
    output_hash: str  # SHA-256 of canonical output
    receipt_hash: Optional[str]  # Hash of the receipt for this stage, if any
    prev_hash: str  # Hash of the previous entry (chain)
    self_hash: str  # Hash of this entry
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "stage": self.stage,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "receipt_hash": self.receipt_hash,
            "prev_hash": self.prev_hash,
            "self_hash": self.self_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FlightEntry":
        return cls(
            seq=d["seq"],
            timestamp=d["timestamp"],
            stage=d["stage"],
            input_hash=d["input_hash"],
            output_hash=d["output_hash"],
            receipt_hash=d.get("receipt_hash"),
            prev_hash=d["prev_hash"],
            self_hash=d["self_hash"],
            metadata=d.get("metadata", {}),
        )


def _canonical_hash(data: Any) -> str:
    """SHA-256 hash of canonical JSON representation."""
    if isinstance(data, str):
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _entry_hash(entry_dict: Dict[str, Any]) -> str:
    """Compute the self_hash for a flight entry (with self_hash emptied)."""
    temp = dict(entry_dict)
    temp["self_hash"] = ""
    canonical = json.dumps(temp, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FlightLog:
    """
    Flight recorder log — a hash-chained sequence of execution entries.

    Usage:
        log = FlightLog()
        log.add_entry("ingest", input_data, output_data, receipt_hash)
        log.add_entry("extract", input_data, output_data, receipt_hash)
        log.save(path)

        # Later: verify
        violations = verify_flight_log(path)
    """

    def __init__(self, agent_id: str = "") -> None:
        self.agent_id = agent_id
        self.entries: List[FlightEntry] = []
        self._prev_hash = "genesis"

    def add_entry(
        self,
        stage: str,
        input_data: Any,
        output_data: Any,
        receipt_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FlightEntry:
        """Add a new entry to the flight log."""
        seq = len(self.entries)
        entry_dict = {
            "seq": seq,
            "timestamp": int(time.time()),
            "stage": stage,
            "input_hash": _canonical_hash(input_data),
            "output_hash": _canonical_hash(output_data),
            "receipt_hash": receipt_hash,
            "prev_hash": self._prev_hash,
            "self_hash": "",
            "metadata": metadata or {},
        }
        entry_dict["self_hash"] = _entry_hash(entry_dict)
        entry = FlightEntry.from_dict(entry_dict)
        self.entries.append(entry)
        self._prev_hash = entry.self_hash
        return entry

    @property
    def root_hash(self) -> str:
        """The hash of the last entry (chain head). Empty if no entries."""
        return self.entries[-1].self_hash if self.entries else "genesis"

    @property
    def merkle_root_of_receipts(self) -> Optional[str]:
        """Merkle root of all receipt hashes (if any receipts recorded)."""
        receipt_hashes = [
            e.receipt_hash for e in self.entries if e.receipt_hash is not None
        ]
        if not receipt_hashes:
            return None
        # Use the existing merkle module
        from kairo.trust.merkle import merkle_root

        leaves = [h.encode("ascii") for h in receipt_hashes]
        return merkle_root(leaves)

    def save(self, path: Path) -> None:
        """Save the flight log to a JSONL file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: Path) -> "FlightLog":
        """Load a flight log from a JSONL file."""
        path = Path(path)
        log = cls()
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = FlightEntry.from_dict(json.loads(line))
                    log.entries.append(entry)
                    log._prev_hash = entry.self_hash
        return log


def record_flight(
    stages: List[Dict[str, Any]],
    agent_id: str = "",
) -> FlightLog:
    """
    Record a flight log from a list of stage dictionaries.

    Each stage dict should have:
        - stage: name of the stage
        - input: input data (any JSON-serializable)
        - output: output data (any JSON-serializable)
        - receipt_hash: optional hash of the receipt for this stage
        - metadata: optional metadata dict
    """
    log = FlightLog(agent_id=agent_id)
    for s in stages:
        log.add_entry(
            stage=s["stage"],
            input_data=s["input"],
            output_data=s["output"],
            receipt_hash=s.get("receipt_hash"),
            metadata=s.get("metadata"),
        )
    return log


def verify_flight_log(path: Path) -> List[str]:
    """
    Verify a flight log file: check hash chain integrity and self_hash correctness.

    Returns a list of violation strings (empty = valid).
    """
    path = Path(path)
    if not path.exists():
        return [f"Flight log not found: {path}"]

    violations: List[str] = []
    prev_hash = "genesis"

    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                violations.append(f"Line {line_num}: invalid JSON ({e})")
                continue

            # Verify self_hash
            computed = _entry_hash(entry)
            if computed != entry.get("self_hash"):
                violations.append(
                    f"Entry seq={entry.get('seq')}: self_hash mismatch "
                    f"(computed={computed[:16]}..., stored={entry.get('self_hash', '')[:16]}...)"
                )

            # Verify chain linkage
            if entry.get("prev_hash") != prev_hash:
                violations.append(
                    f"Entry seq={entry.get('seq')}: prev_hash mismatch "
                    f"(expected={prev_hash[:16]}..., got={entry.get('prev_hash', '')[:16]}...)"
                )

            prev_hash = entry.get("self_hash", "")

    return violations


def replay_flight(
    path: Path,
    expected_merkle_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Replay a flight log and verify its integrity.

    Returns a dict with:
        - valid: bool (no violations)
        - violations: list of violation strings
        - entry_count: number of entries
        - root_hash: hash of the last entry
        - merkle_root: Merkle root of receipt hashes (if any)
        - expected_merkle_root: the expected root (if provided)
        - merkle_root_matches: bool (if expected was provided)
    """
    path = Path(path)
    violations = verify_flight_log(path)
    log = FlightLog.load(path)

    result: Dict[str, Any] = {
        "valid": len(violations) == 0,
        "violations": violations,
        "entry_count": len(log.entries),
        "root_hash": log.root_hash,
        "merkle_root": log.merkle_root_of_receipts,
    }

    if expected_merkle_root is not None:
        result["expected_merkle_root"] = expected_merkle_root
        actual = log.merkle_root_of_receipts
        result["merkle_root_matches"] = (
            actual is not None and actual == expected_merkle_root
        )
        if not result["merkle_root_matches"]:
            result["violations"].append(
                f"Merkle root mismatch: expected={expected_merkle_root[:16]}..., "
                f"got={actual[:16] if actual else 'None'}..."
            )
            result["valid"] = False

    return result
