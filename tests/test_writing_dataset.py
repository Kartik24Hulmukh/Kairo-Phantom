"""
tests/test_writing_dataset.py

Validates the generated 5,000-pair writing registers dataset for format, schemas, and counts.
"""

import json
import unittest
from pathlib import Path

DATASET_PATH = Path(__file__).parent.parent / "training_data" / "kairo_writing_dataset_5k.jsonl"

if not DATASET_PATH.exists():
    raise unittest.SkipTest(
        "training_data dataset ships as a release asset — see RELEASING.md"
    )


def test_writing_dataset_validation():
    """Verify that the generated dataset is valid SFT instruction data."""
    dataset_path = Path(__file__).parent.parent / "training_data" / "kairo_writing_dataset_5k.jsonl"
    
    assert dataset_path.exists(), f"Dataset file not found at {dataset_path}"
    
    lines = dataset_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5000, f"Expected exactly 5000 examples, got {len(lines)}"
    
    registers = {"victorian", "journalism", "legal", "scientific", "business"}
    found_registers = set()
    
    for idx, line in enumerate(lines):
        # Verify valid JSON
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON at line {idx + 1}: {e}")
            
        # Verify keys
        assert "instruction" in data
        assert "input" in data
        assert "output" in data
        
        # Verify input schema
        input_data = json.loads(data["input"])
        assert "document_context" in input_data
        assert "mem_context" in input_data
        
        doc_ctx = input_data["document_context"]
        assert "register" in doc_ctx
        assert "target_length_words" in doc_ctx
        assert "persona_target" in doc_ctx
        
        reg_name = doc_ctx["register"]
        assert reg_name in registers
        found_registers.add(reg_name)
        
        # Verify output schema
        output_data = json.loads(data["output"])
        assert "text" in output_data
        assert "register" in output_data
        assert "persona" in output_data
        assert "word_count" in output_data
        
        assert output_data["register"] == reg_name
        assert len(output_data["text"]) > 0
        assert output_data["word_count"] == len(output_data["text"].split())

    # Verify all registers are represented
    assert found_registers == registers
