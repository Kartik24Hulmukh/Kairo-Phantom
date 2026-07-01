import sys
import tracemalloc
from pathlib import Path
from unittest.mock import MagicMock

# Mock the ollama module in sys.modules to avoid ImportErrors when package is not installed
mock_ollama = MagicMock()
sys.modules["ollama"] = mock_ollama

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.intent_gate import IntentGate


def test_memory_leak_classification_loop():
    # Set up mock response for ollama.chat
    mock_response = {
        "message": {
            "content": '{"intent": "rewrite", "domain": "word", "target_element": "paragraph", "confidence": 0.95}'
        }
    }

    mock_ollama.chat.return_value = mock_response

    gate = IntentGate()

    tracemalloc.start()

    # Take snapshot 1
    snapshot1 = tracemalloc.take_snapshot()

    # Run 1000 classify iterations
    for i in range(1000):
        gate.classify(f"Instruction number {i}", app_name="word")

    # Take snapshot 2
    snapshot2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Calculate memory differences
    stats = snapshot2.compare_to(snapshot1, "lineno")
    total_growth_bytes = sum(stat.size_diff for stat in stats)
    total_growth_mb = total_growth_bytes / (1024 * 1024)

    # Assert memory growth is under 50MB
    assert (
        total_growth_mb < 50.0
    ), f"Memory growth was {total_growth_mb:.2f}MB, exceeding 50MB threshold."
