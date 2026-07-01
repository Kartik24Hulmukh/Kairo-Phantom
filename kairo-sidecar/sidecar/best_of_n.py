"""
sidecar/best_of_n.py — Best-of-N candidate selection using deterministic oracles.
Scores N candidates at inference time using docx/xlsx/pptx/pdf oracles.
"""

import os
import shutil
import logging
from typing import List, Any, Type
from pydantic import BaseModel

from sidecar.llm_caller import call_with_schema
from sidecar.oracles import verify_docx, verify_xlsx, verify_pptx, verify_pdf

log = logging.getLogger("kairo-sidecar.best_of_n")


def run_best_of_n(
    prompt: str,
    schema_class: Type[BaseModel],
    model: str,
    domain: str,
    file_path: str,
    master: Any,
    doc_context: Any,
    N: int = 3,
) -> BaseModel:
    """
    Generates N candidate responses from LLM, applies each to a temporary copy of the document,
    runs the appropriate oracle, and returns the highest scoring candidate.
    """
    if N <= 1 or not file_path or not os.path.exists(file_path):
        # Fallback to standard single execution
        return call_with_schema(prompt, schema_class, model=model)

    candidates: List[BaseModel] = []
    scores: List[float] = []

    log.info(f"[Best-of-N] Generating {N} candidates for domain '{domain}' on file '{file_path}'")

    for i in range(N):
        try:
            # We call LLM. Since temperature might be fixed at 0.0 in call_with_schema, we can vary the prompt slightly
            # or try to get diversity. Let's add a small variation to the prompt to encourage diverse output candidates if needed,
            # but if the LLM is slightly non-deterministic or we pass a seed/variation, it will be different.
            variant_prompt = prompt
            if i > 0:
                variant_prompt += f"\n[Candidate Option {i+1}]: Be extra precise and double check your constraints."

            candidate = call_with_schema(variant_prompt, schema_class, model=model)
            candidates.append(candidate)
        except Exception as e:
            log.warning(f"[Best-of-N] Failed to generate candidate {i+1}: {e}")
            continue

    if not candidates:
        # If all candidate generations fail, fall back to standard call
        return call_with_schema(prompt, schema_class, model=model)

    # Temporary directory for copy operations
    temp_dir = file_path + "_best_of_n_temp"
    os.makedirs(temp_dir, exist_ok=True)

    for i, candidate in enumerate(candidates):
        temp_file = os.path.join(temp_dir, f"candidate_{i}{os.path.splitext(file_path)[1]}")
        try:
            shutil.copy2(file_path, temp_file)

            # Apply candidate operations to temp file
            # validate_operations and apply_operations can modify file
            validated_ops = master.validate_operations(candidate, doc_context)
            # Apply using master's writer/apply logic
            if domain == "word":
                from sidecar.writers.docx_writer import write_docx

                # validated_ops is a list of DocxOperation
                write_docx(
                    temp_file,
                    [op.model_dump() if hasattr(op, "model_dump") else op for op in validated_ops],
                )

                # Score using verify_docx
                try:
                    verify_docx(temp_file)
                    score = 1.0
                except AssertionError:
                    score = 0.0

            elif domain == "excel":
                from sidecar.writers.xlsx_writer import write_xlsx

                write_xlsx(
                    temp_file,
                    [op.model_dump() if hasattr(op, "model_dump") else op for op in validated_ops],
                )

                try:
                    # Collect cell formulas or values to verify
                    cell_formulas = {}
                    cell_values = {}
                    for op in validated_ops:
                        # validated_ops is ExcelOperation list
                        cell_ref = getattr(op, "cell", None) or op.get("cell")
                        formula = getattr(op, "formula", "") or op.get("formula", "")
                        value = getattr(op, "value", "") or op.get("value", "")
                        if formula:
                            cell_formulas[cell_ref] = formula
                        elif value:
                            cell_values[cell_ref] = value

                    verify_xlsx(temp_file, cell_values=cell_values, cell_formulas=cell_formulas)
                    score = 1.0
                except AssertionError:
                    score = 0.0

            elif domain == "powerpoint":
                from sidecar.writers.pptx_writer import write_pptx

                write_pptx(
                    temp_file,
                    [op.model_dump() if hasattr(op, "model_dump") else op for op in validated_ops],
                )

                try:
                    verify_pptx(temp_file)
                    score = 1.0
                except AssertionError:
                    score = 0.0

            elif domain == "pdf":
                # PDF oracle: verify readability and expected text substrings extracted from candidate
                try:
                    # Collect expected text substrings from candidate fields
                    expected_substrings: list[str] = []
                    if hasattr(candidate, "model_fields"):
                        for field_name in candidate.model_fields:
                            val = getattr(candidate, field_name, None)
                            if isinstance(val, str) and len(val) > 3:
                                expected_substrings.append(val[:80])
                    elif isinstance(candidate, dict):
                        for val in candidate.values():
                            if isinstance(val, str) and len(val) > 3:
                                expected_substrings.append(val[:80])

                    verify_pdf(temp_file, expected_substrings=expected_substrings or None)
                    score = 1.0
                except AssertionError:
                    score = 0.5  # Partial score: PDF is readable but content mismatch
                except Exception:
                    score = 0.0

            else:
                score = 1.0  # Default fallback score for unhandled domains

            scores.append(score)
            log.info(f"[Best-of-N] Candidate {i+1} scored: {score}")
        except Exception as e:
            log.warning(f"[Best-of-N] Candidate {i+1} evaluation failed: {e}")
            scores.append(0.0)
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    # Clean up temp dir
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    # Select best candidate
    best_index = 0
    best_score = -1.0
    for idx, score in enumerate(scores):
        if score > best_score:
            best_score = score
            best_index = idx

    log.info(f"[Best-of-N] Selected candidate {best_index+1} with score {best_score}")
    return candidates[best_index]
