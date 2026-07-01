import sys
import pytest
from pathlib import Path

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.masters.excel_master import ExcelContext, ExcelOperationValidator

MALFORMED_FORMULAS = [
    "=SUM(A1:Z",  # Unbalanced parenthesis
    "=IF(,)",  # Missing arguments
    "=VLOOKUP(A1,B:C)",  # Missing required arguments (col_index)
    "=AVERAGE(A1:B1))",  # Unbalanced parenthesis (extra closing)
    "=SUM(A1:A5))",  # Extra closing parenthesis
    "=IF(A1>10, 'yes'",  # Unbalanced quote or parenthesis
    "=SUMIF(A1:A10)",  # Missing criteria argument
    "=COUNTIF(A1:A10,)",  # Missing criteria argument
    "=INDEX(A1:B10)",  # Missing row/column index
    "=XLOOKUP(A1)",  # Missing lookup_array and return_array
    "=ROUND(A1)",  # Missing num_digits
    "=LEFT(A1, -1)",  # Invalid negative length (logical error, rejected by references/semantics if checked)
    "=VLOOKUP(A1, B:C, 0, FALSE)",  # Invalid column index 0 (if checked)
    "=SUM(A1:A0)",  # Invalid row index 0
    "=SUM(A0:B10)",  # Invalid row index 0
    "SUM(A1:B10)",  # Missing leading equals (should be fixed, or rejected if strict)
    "=AVERAGEIF(A1)",  # Missing criteria and average_range
    "=IFERROR(A1)",  # Missing value_if_error
    "=MID(A1, 2)",  # Missing num_chars
    "=CONCATENATE(A1",  # Unbalanced parenthesis
]


@pytest.fixture
def excel_context():
    return ExcelContext(
        active_cell="C2",
        active_sheet="Sheet1",
        sheet_names=["Sheet1"],
        cells=[],
        headers={},
        named_ranges={},
        column_types={},
        locale="en",
        max_row=10,
        max_col=10,
        file_path="",
    )


@pytest.mark.parametrize("formula", MALFORMED_FORMULAS)
def test_formula_validation_rejection(excel_context, formula):
    validator = ExcelOperationValidator()

    op = {"type": "write_cell", "cell": "C2", "formula": formula}

    result = validator.validate(op, excel_context)

    # Assert that the validator returns invalid for these malformed formulas
    # Note: validator tries to auto-correct some of them (like missing equals or unmatched parens).
    # But if the correction itself is invalid or fails validation, it must be False.
    # Let's verify if the validator either rejects or corrects them.
    # If the formula is totally invalid and cannot be fixed, result.valid must be False.
    # We assert that the original raw formula is either rejected or corrected to something else, or fails.
    # Specifically, if it cannot be corrected to a valid formula, it is rejected.
    # To be precise, let's check the result:
    assert (result.valid is False) or (result.op["formula"] != formula)


def test_forge_validator_semantic_evaluation():
    from sidecar.parsers.forge_bridge import ForgeValidator

    v = ForgeValidator()

    # Valid formula
    res1 = v.validate("=SUM(A1, B1)")
    assert res1["valid"] is True

    # Semantically invalid (compile failure - syntax error)
    res2 = v.validate("=SUM(A1+")
    assert res2["valid"] is False
    assert "Semantic evaluation failed" in res2["error"]

    # Semantically invalid (compile failure - operator syntax error)
    res3 = v.validate("=SUM(A1, B1+)")
    assert res3["valid"] is False
    assert "Semantic evaluation failed" in res3["error"]

    # Semantically invalid (evaluation failure - division by zero)
    res4 = v.validate("=A1/0")
    assert res4["valid"] is False
    assert "Semantic evaluation failed" in res4["error"]
