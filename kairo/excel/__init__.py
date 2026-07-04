# PROVENANCE: original | clean-room Excel domain engine per prompts/domains/08c_excel.md
"""kairo.excel — Excel domain with real formula recompute + oracle verification.

Re-exports the public API from ``kairo.excel.engine``.
"""

from kairo.excel.engine import (
    ExcelEdit,
    ExcelResult,
    FlaggedCell,
    LibreOfficeUnavailableError,
    independent_calc_financial_model,
    independent_calc_pivot_aggregation,
    excel_pipeline,
    read_formulas,
    read_recomputed_values,
    recompute_xlsx,
    xlsx_recompute,
    xlsx_structure_readback,
)

__all__ = [
    "ExcelEdit",
    "ExcelResult",
    "FlaggedCell",
    "LibreOfficeUnavailableError",
    "independent_calc_financial_model",
    "independent_calc_pivot_aggregation",
    "excel_pipeline",
    "read_formulas",
    "read_recomputed_values",
    "recompute_xlsx",
    "xlsx_recompute",
    "xlsx_structure_readback",
]
