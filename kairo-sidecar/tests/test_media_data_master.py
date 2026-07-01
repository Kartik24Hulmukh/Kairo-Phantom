import os
import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.masters.other_masters import MediaMaster, DataMaster
from sidecar.schemas.domain_schemas import MediaResponse, DataResponse


# ==========================================
# MediaMaster Tests
# ==========================================


def test_media_master_extract_context_default():
    master = MediaMaster()
    ctx = master.extract_context(None, None)
    assert ctx["active_app"] == "Canva"
    assert ctx["app_type"] == "graphic_editor"
    assert ctx["injection_path"] == "clipboard"
    assert "layers" in ctx
    assert "canvas_elements" in ctx


def test_media_master_detects_davinci_resolve():
    master = MediaMaster()
    ctx = master.extract_context("C:/Projects/my_project.drp", None)
    assert ctx["active_app"] == "DaVinci Resolve"
    assert ctx["app_type"] == "video_editor"
    assert ctx["injection_path"] == "script"


def test_media_master_detects_after_effects():
    master = MediaMaster()
    ctx = master.extract_context("C:/Projects/composition.aep", None)
    assert ctx["active_app"] == "After Effects"
    assert ctx["app_type"] == "video_editor"
    assert ctx["injection_path"] == "script"


def test_media_master_detects_photoshop():
    master = MediaMaster()
    ctx = master.extract_context("C:/Projects/design.psd", None)
    assert ctx["active_app"] == "Adobe Photoshop"
    assert ctx["injection_path"] == "uia"


def test_media_master_canva_clipboard_path():
    master = MediaMaster()
    ctx = master.extract_context("canva.com/design/abc123", None)
    assert ctx["active_app"] == "Canva"
    assert ctx["injection_path"] == "clipboard"


def test_media_master_build_prompt():
    master = MediaMaster()
    context = {
        "active_app": "Canva",
        "app_type": "graphic_editor",
        "timeline_scrubber_seconds": 0,
        "injection_path": "clipboard",
    }
    prompt = master.build_prompt("add caption", context, mem_context="")
    assert "SYSTEM" in prompt or "Media" in prompt
    assert "Canva" in prompt
    assert "add caption" in prompt


def test_media_master_validate_operations():
    master = MediaMaster()
    resp = MediaResponse(
        injection_method="clipboard",
        content="Photo by John Doe",
        platform="canva",
        confidence=0.9,
        media_type="graphic",
        grp_display_text="Add this caption to your Canva element",
    )
    ops = master.validate_operations(resp, {})
    assert len(ops) == 1
    assert ops[0]["injection_method"] == "clipboard"


def test_media_master_get_schema_class():
    master = MediaMaster()
    assert master.get_schema_class() == MediaResponse


# ==========================================
# DataMaster Tests
# ==========================================


def test_data_master_extract_context_default():
    master = DataMaster()
    ctx = master.extract_context(None, None)
    assert ctx["notebook_cell_count"] == 1
    assert ctx["kernel_active"] is True
    assert ctx["imports"] == []
    assert ctx["language"] == "python"


def test_data_master_detects_jupyter_notebook():
    master = DataMaster()
    # Create a temp .ipynb file
    with tempfile.NamedTemporaryFile(
        suffix=".ipynb", mode="w", delete=False, encoding="utf-8"
    ) as f:
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": [
                        "import pandas as pd\n",
                        "import numpy as np\n",
                        "df = pd.DataFrame()\n",
                    ],
                },
                {"cell_type": "markdown", "source": ["# Title"]},
                {
                    "cell_type": "code",
                    "source": ["from sklearn.model_selection import train_test_split\n"],
                },
            ]
        }
        json.dump(nb, f)
        temp_path = f.name

    try:
        ctx = master.extract_context(temp_path, 0)
        assert ctx["language"] == "python"
        assert ctx["notebook_cell_count"] == 3
        assert "pandas" in ctx["imports"]
        assert "numpy" in ctx["imports"]
        assert "sklearn" in ctx["imports"]
        assert "pandas" in ctx["data_libraries"]
        assert "numpy" in ctx["data_libraries"]
    finally:
        os.unlink(temp_path)


def test_data_master_detects_sql_tsql_dialect():
    master = DataMaster()
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False, encoding="utf-8") as f:
        f.write("SELECT TOP 10 * FROM Customers WHERE @@ROWCOUNT > 0;\n")
        temp_path = f.name

    try:
        ctx = master.extract_context(temp_path, None)
        assert ctx["language"] == "sql"
        assert ctx["sql_dialect"] == "T-SQL"
    finally:
        os.unlink(temp_path)


def test_data_master_detects_sql_postgresql_dialect():
    master = DataMaster()
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False, encoding="utf-8") as f:
        f.write("SELECT * FROM orders WHERE status='active' LIMIT 100;\n")
        temp_path = f.name

    try:
        ctx = master.extract_context(temp_path, None)
        assert ctx["sql_dialect"] == "PostgreSQL"
    finally:
        os.unlink(temp_path)


def test_data_master_detects_r_language():
    master = DataMaster()
    with tempfile.NamedTemporaryFile(suffix=".r", mode="w", delete=False, encoding="utf-8") as f:
        f.write("library(dplyr)\ndf <- read.csv('data.csv')\n")
        temp_path = f.name

    try:
        ctx = master.extract_context(temp_path, None)
        assert ctx["language"] == "r"
    finally:
        os.unlink(temp_path)


def test_data_master_detects_python_data_libraries():
    master = DataMaster()
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(
            "import pandas as pd\nimport matplotlib.pyplot as plt\nfrom sklearn import datasets\n"
        )
        temp_path = f.name

    try:
        ctx = master.extract_context(temp_path, 5)
        assert ctx["language"] == "python"
        assert "pandas" in ctx["imports"]
        assert "matplotlib" in ctx["imports"]
        assert "sklearn" in ctx["imports"]
        assert "pandas" in ctx["data_libraries"]
        assert ctx["cursor_line"] == 5
    finally:
        os.unlink(temp_path)


def test_data_master_build_prompt_includes_language():
    master = DataMaster()
    context = {
        "language": "sql",
        "sql_dialect": "T-SQL",
        "data_libraries": [],
        "imports": [],
        "notebook_cell_count": 1,
        "cursor_line": 10,
        "file_path": "C:/queries/report.sql",
    }
    prompt = master.build_prompt("write a query to get top customers", context, mem_context="")
    assert "sql" in prompt.lower()
    assert "T-SQL" in prompt
    assert "cross-dialect" in prompt.lower() or "dialect" in prompt.lower()
    assert "write a query to get top customers" in prompt


def test_data_master_build_prompt_python_idioms():
    master = DataMaster()
    context = {
        "language": "python",
        "sql_dialect": "generic",
        "data_libraries": ["pandas", "numpy"],
        "imports": ["pandas", "numpy"],
        "notebook_cell_count": 5,
        "cursor_line": 3,
        "file_path": "analysis.py",
    }
    prompt = master.build_prompt(
        "group by region and sum sales", context, mem_context="Use vectorized ops"
    )
    assert "pandas" in prompt.lower() or "numpy" in prompt.lower()
    assert "vectorized" in prompt.lower()
    assert "group by region and sum sales" in prompt


def test_data_master_validate_operations():
    master = DataMaster()
    resp = DataResponse(
        injection_method="clipboard",
        content="df.groupby('region')['sales'].sum()",
        language="python",
        confidence=0.92,
    )
    ops = master.validate_operations(resp, {})
    assert len(ops) == 1
    assert "language" in ops[0]


def test_data_master_get_schema_class():
    master = DataMaster()
    assert master.get_schema_class() == DataResponse
