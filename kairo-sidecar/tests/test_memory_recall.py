import os
import sys
import tempfile
from pathlib import Path

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.mem_machine import MemMachineClient


def test_mem_machine_cross_session_recall():
    # Create a temp file path for the SQLite database
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        # Session 1: Create client, record user preference
        client1 = MemMachineClient(db_path=temp_db_path)
        client1.record_interaction(
            domain="word",
            task_type="writing",
            user_prompt="draft an offer letter",
            style_notes="User prefers signature closing with 'Warm regards'",
        )

        # Simulate restart by deleting client1 reference
        del client1

        # Session 2: Create new client instance loading the same DB file
        client2 = MemMachineClient(db_path=temp_db_path)
        notes = client2.query(domain="word")

        # Verify that preference recorded in Session 1 is correctly recalled in Session 2
        assert (
            "warm regards" in notes.lower()
        ), f"Expected preference not found in retrieved memory: {notes}"

    finally:
        # Clean up database file
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except Exception:
                pass
