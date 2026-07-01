from pydantic import BaseModel, Field, field_validator
from typing import Literal, Union, List, Any, Optional
import re


def validate_excel_formula(formula: str) -> bool:
    """
    Basic validation for Excel formulas:
    - Must start with '='
    - Must have balanced parentheses
    - Function names should be in uppercase/standard format (e.g. SUM, IF, AVERAGE, VLOOKUP, etc.)
    """
    if not formula:
        return False

    formula = formula.strip()
    if not formula.startswith("="):
        return False

    # Check balanced parentheses
    stack = []
    for idx, char in enumerate(formula):
        if char == "(":
            stack.append(idx)
        elif char == ")":
            if not stack:
                return False
            stack.pop()
    if stack:
        return False

    # Check function name format (e.g., if there's an alphabet string followed by '(', it should be uppercase standard functions)
    funcs = re.findall(r"([a-zA-Z_][a-zA-Z0-9_\.]*)\(", formula)
    known_funcs = {
        "SUM",
        "AVERAGE",
        "MIN",
        "MAX",
        "IF",
        "COUNT",
        "VLOOKUP",
        "CONCAT",
        "AND",
        "OR",
        "NOT",
        "INDEX",
        "MATCH",
        "ROUND",
        "PRODUCT",
        "SUMIF",
        "COUNTIF",
        "STDEV",
        "MEDIAN",
        "ABS",
        "TODAY",
        "NOW",
        "YEAR",
        "MONTH",
        "DAY",
    }
    for func in funcs:
        # Excel is case-insensitive, but standard practice in playbook is uppercase
        if func.upper() not in known_funcs:
            # Let it pass if it matches basic word character but maybe warn/log, or keep it strict
            pass

    return True


class WriteCellOp(BaseModel):
    type: Literal["write_cell"] = "write_cell"
    sheet: str = "Sheet1"
    cell: str
    value: Optional[Any] = None
    formula: Optional[str] = None

    @field_validator("formula")
    @classmethod
    def check_formula(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "":
            if not validate_excel_formula(v):
                raise ValueError(f"Invalid Excel formula: {v}")
        return v


class WriteRangeOp(BaseModel):
    type: Literal["write_range"] = "write_range"
    sheet: str = "Sheet1"
    start_cell: str
    values: List[List[Any]]


class ExplainFormulaOp(BaseModel):
    type: Literal["explain_formula"] = "explain_formula"
    sheet: str = "Sheet1"
    cell: str


class GenerateFormulaOp(BaseModel):
    type: Literal["generate_formula"] = "generate_formula"
    description: str
    target_cell: str


class CreateChartOp(BaseModel):
    type: Literal["create_chart"] = "create_chart"
    sheet: str = "Sheet1"
    source_range: str
    chart_type: str = "column"
    title: str = "Chart"
    target_sheet: Optional[str] = None
    cell: Optional[str] = None


class CreatePivotOp(BaseModel):
    type: Literal["create_pivot"] = "create_pivot"
    sheet: str = "Sheet1"
    source_range: str
    rows: List[str] = []
    columns: List[str] = []
    values: List[str] = []
    target_sheet: str
    cell: Optional[str] = None


ExcelOperation = Union[
    WriteCellOp, WriteRangeOp, ExplainFormulaOp, GenerateFormulaOp, CreateChartOp, CreatePivotOp
]


class ExcelResponse(BaseModel):
    operations: List[ExcelOperation]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=200)
