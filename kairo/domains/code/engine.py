# PROVENANCE: original | clean-room Code domain engine per DOMAIN_BUILD_TEMPLATE.md
"""Code domain engine — real parse/compile/test verification via tree-sitter + py_compile + pytest.

Implements the ``compile_test_pass`` and ``parse_validity`` oracles from
specs/VERIFICATION_ORACLES.md for the Code domain.

ARCHITECTURE:
  1. tree-sitter (MIT) parses .py files and checks for ERROR nodes (syntax validity).
  2. py_compile (stdlib) byte-compiles .py files (catches syntax errors at CPython level).
  3. pytest (MIT) runs the project's test suite (catches logic errors).
  4. The oracle runs all three on the fixture project after an edit.

SCOPE: V1 is PYTHON ONLY (deterministic, offline, stdlib-only fixture).
Other languages = Experimental (honest label).

HONEST DEGRADATION:
  If python/pytest/tree-sitter is not installed, the engine FAILS LOUD:
  "code toolchain unavailable — install python3, pytest, tree-sitter"
  It NEVER claims pass without a real run.

Dependencies (all permissive — MIT):
  - tree-sitter (MIT) — incremental parsing
  - tree-sitter-python (MIT) — Python grammar for tree-sitter
  - pytest (MIT) — test runner (already in requirements-test.txt)

All operations are fully offline. No network calls. No LLM. No cloud.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

log = logging.getLogger("kairo.code")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CodeToolchainUnavailableError(RuntimeError):
    """Raised when python/pytest/tree-sitter is not installed — honest degradation."""

    pass


class CodeError(RuntimeError):
    """Raised when a code operation fails."""

    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ParseResult:
    """Result of tree-sitter parse validity check."""

    file_path: str
    has_errors: bool
    error_count: int
    error_nodes: list[str] = dc_field(default_factory=list)


@dataclass
class CompileResult:
    """Result of py_compile check."""

    file_path: str
    success: bool
    error: str = ""


@dataclass
class TestResult:
    """Result of pytest run."""

    exit_code: int
    passed: int
    failed: int
    errors: int
    output: str = ""


@dataclass
class CodeResult:
    """Structured result of a code pipeline run."""

    ok: bool
    parse_results: list[ParseResult] = dc_field(default_factory=list)
    compile_results: list[CompileResult] = dc_field(default_factory=list)
    test_result: TestResult | None = None
    error: str = ""
    audit_log_json: str = ""
    egress_report_json: str = ""
    doc_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "parse_errors": sum(1 for p in self.parse_results if p.has_errors),
            "compile_failures": sum(1 for c in self.compile_results if not c.success),
            "test_passed": self.test_result.passed if self.test_result else 0,
            "test_failed": self.test_result.failed if self.test_result else 0,
            "error": self.error,
            "doc_hash": self.doc_hash,
        }


# ---------------------------------------------------------------------------
# Toolchain availability checks
# ---------------------------------------------------------------------------


def _check_tree_sitter() -> bool:
    """Check if tree-sitter and tree-sitter-python are available."""
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_python  # noqa: F401

        return True
    except ImportError:
        return False


def _check_pytest() -> bool:
    """Check if pytest is available."""
    try:
        import pytest  # noqa: F401

        return True
    except ImportError:
        return False


def _check_python() -> bool:
    """Check if python3 is available (always true in our environment)."""
    return sys.executable is not None and Path(sys.executable).exists()


# ---------------------------------------------------------------------------
# Parse validity (tree-sitter)
# ---------------------------------------------------------------------------


def parse_file(file_path: str) -> ParseResult:
    """Parse a .py file with tree-sitter and check for ERROR nodes.

    Args:
        file_path: Path to the .py file.

    Returns:
        ParseResult with has_errors, error_count, and error node descriptions.

    Raises:
        CodeToolchainUnavailableError: If tree-sitter is not installed.
        CodeError: If the file cannot be read.
    """
    if not _check_tree_sitter():
        raise CodeToolchainUnavailableError(
            "code toolchain unavailable — install tree-sitter and tree-sitter-python "
            "to enable parse validity checks. The Code domain cannot proceed "
            "without tree-sitter."
        )

    from tree_sitter import Language, Parser
    import tree_sitter_python as tspython

    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except Exception as e:
        raise CodeError(f"Failed to read file: {e}") from e

    language = Language(tspython.language())
    parser = Parser(language)
    tree = parser.parse(source)

    error_nodes: list[str] = []

    def _walk(node):
        if node.type == "ERROR":
            error_nodes.append(
                f"ERROR at line {node.start_point[0] + 1}, col {node.start_point[1]}"
            )
        if node.type == "ERROR_SENTINEL":
            error_nodes.append(f"ERROR_SENTINEL at line {node.start_point[0] + 1}")
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)

    return ParseResult(
        file_path=file_path,
        has_errors=len(error_nodes) > 0,
        error_count=len(error_nodes),
        error_nodes=error_nodes,
    )


# ---------------------------------------------------------------------------
# Compile check (py_compile)
# ---------------------------------------------------------------------------


def compile_file(file_path: str) -> CompileResult:
    """Byte-compile a .py file using py_compile.

    Args:
        file_path: Path to the .py file.

    Returns:
        CompileResult with success status and error message.
    """
    import py_compile

    try:
        py_compile.compile(file_path, doraise=True)
        return CompileResult(file_path=file_path, success=True)
    except py_compile.PyCompileError as e:
        return CompileResult(file_path=file_path, success=False, error=str(e))
    except Exception as e:
        return CompileResult(file_path=file_path, success=False, error=str(e))


# ---------------------------------------------------------------------------
# Test run (pytest)
# ---------------------------------------------------------------------------


def run_tests(project_dir: str) -> TestResult:
    """Run pytest on a project directory.

    Args:
        project_dir: Path to the project directory containing tests/.

    Returns:
        TestResult with exit code, passed/failed/errors counts, and output.

    Raises:
        CodeToolchainUnavailableError: If pytest is not installed.
    """
    if not _check_pytest():
        raise CodeToolchainUnavailableError(
            "code toolchain unavailable — install pytest to run tests."
        )

    project_path = str(Path(project_dir).resolve())

    # Run pytest as a subprocess for isolation
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        project_path,
        "-v",
        "--tb=short",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_path,
        )
    except subprocess.TimeoutExpired:
        return TestResult(exit_code=-1, passed=0, failed=0, errors=1, output="TIMEOUT")
    except Exception as e:
        return TestResult(exit_code=-1, passed=0, failed=0, errors=1, output=str(e))

    output = proc.stdout + proc.stderr

    # Parse pytest output for pass/fail counts
    passed = 0
    failed = 0
    errors = 0

    for line in output.splitlines():
        if " passed" in line and "failed" not in line.lower():
            # e.g. "3 passed in 0.01s"
            import re

            m = re.search(r"(\d+)\s+passed", line)
            if m:
                passed = int(m.group(1))
        if "failed" in line.lower():
            import re

            m = re.search(r"(\d+)\s+failed", line)
            if m:
                failed = int(m.group(1))
        if "error" in line.lower():
            import re

            m = re.search(r"(\d+)\s+error", line)
            if m:
                errors = int(m.group(1))

    # If we couldn't parse, infer from exit code
    if passed == 0 and failed == 0 and errors == 0:
        if proc.returncode == 0:
            # Count "PASSED" in verbose output
            passed = output.count("PASSED")
        else:
            failed = output.count("FAILED")
            errors = output.count("ERROR")

    return TestResult(
        exit_code=proc.returncode,
        passed=passed,
        failed=failed,
        errors=errors,
        output=output[-2000:] if len(output) > 2000 else output,
    )


# ---------------------------------------------------------------------------
# File editing
# ---------------------------------------------------------------------------


def apply_edit(file_path: str, old_text: str, new_text: str) -> str:
    """Apply a text replacement edit to a file.

    Args:
        file_path: Path to the file to edit.
        old_text: Exact text to find (must appear exactly once).
        new_text: Replacement text.

    Returns:
        The absolute path of the edited file.

    Raises:
        CodeError: If old_text is not found or appears multiple times.
    """
    file_path = str(Path(file_path).resolve())

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    count = content.count(old_text)
    if count == 0:
        raise CodeError(f"old_text not found in {file_path}")
    if count > 1:
        raise CodeError(f"old_text appears {count} times in {file_path} — must be unique")

    new_content = content.replace(old_text, new_text, 1)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return file_path


def write_file(file_path: str, content: str) -> str:
    """Write content to a file (create or overwrite).

    Args:
        file_path: Path to the file.
        content: File content.

    Returns:
        The absolute path of the written file.
    """
    file_path = str(Path(file_path).resolve())
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


# ---------------------------------------------------------------------------
# Pipeline with trust stack integration
# ---------------------------------------------------------------------------


def code_pipeline(
    project_dir: str,
    files_to_check: list[str] | None = None,
    private_key: Any = None,
    author: str = "Kairo Code",
) -> CodeResult:
    """Run the code pipeline with trust stack integration.

    1. Parse all .py files via tree-sitter (zero ERROR nodes).
    2. Compile all .py files via py_compile.
    3. Run pytest on the project.
    4. Emit Ed25519 audit log + zero-egress report (if private_key provided).

    Args:
        project_dir: Path to the project directory.
        files_to_check: Optional list of specific .py files to parse+compile.
                        If None, all .py files in project_dir are checked.
        private_key: Optional Ed25519 private key for audit + egress report.
        author: Author name for audit log.

    Returns:
        CodeResult with parse/compile/test results and trust artifacts.
    """
    project_path = Path(project_dir).resolve()

    # Compute doc hash from project files
    hasher = hashlib.sha256()
    if files_to_check is None:
        py_files = sorted(project_path.rglob("*.py"))
    else:
        py_files = [Path(f).resolve() for f in files_to_check]

    for f in py_files:
        if f.exists():
            with open(f, "rb") as fh:
                hasher.update(fh.read())
    doc_hash = hasher.hexdigest()

    # Check toolchain
    if not _check_tree_sitter():
        return CodeResult(
            ok=False,
            error="code toolchain unavailable — install tree-sitter and tree-sitter-python",
            doc_hash=doc_hash,
        )
    if not _check_pytest():
        return CodeResult(
            ok=False,
            error="code toolchain unavailable — install pytest",
            doc_hash=doc_hash,
        )

    # Parse all files
    parse_results: list[ParseResult] = []
    for f in py_files:
        if f.exists() and f.suffix == ".py":
            try:
                pr = parse_file(str(f))
                parse_results.append(pr)
            except (CodeToolchainUnavailableError, CodeError) as e:
                return CodeResult(ok=False, error=str(e), doc_hash=doc_hash)

    # Compile all files
    compile_results: list[CompileResult] = []
    for f in py_files:
        if f.exists() and f.suffix == ".py":
            cr = compile_file(str(f))
            compile_results.append(cr)

    # Run tests
    try:
        test_result = run_tests(str(project_path))
    except CodeToolchainUnavailableError as e:
        return CodeResult(
            ok=False,
            parse_results=parse_results,
            compile_results=compile_results,
            error=str(e),
            doc_hash=doc_hash,
        )

    # Determine overall success
    parse_ok = all(not pr.has_errors for pr in parse_results)
    compile_ok = all(cr.success for cr in compile_results)
    test_ok = test_result.exit_code == 0 and test_result.failed == 0 and test_result.errors == 0
    overall_ok = parse_ok and compile_ok and test_ok

    # Emit audit log + egress report
    audit_log_json = ""
    egress_report_json = ""
    if private_key is not None:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import generate_zero_egress_report

        audit = Ed25519AuditLog(private_key)
        audit.log_run_started(doc_hash=doc_hash, playbook_id="code_pipeline")

        for i, pr in enumerate(parse_results):
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=f"parse_{i}",
                clause_label=f"Parse {Path(pr.file_path).name}: {pr.error_count} errors",
                old_text="",
                new_text=f"tree-sitter parse: {'OK' if not pr.has_errors else 'ERRORS'} ({pr.error_count} errors)",
                citation="tree-sitter",
                rationale="Python file parsed via tree-sitter for syntax validity",
            )

        for i, cr in enumerate(compile_results):
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=f"compile_{i}",
                clause_label=f"Compile {Path(cr.file_path).name}: {'OK' if cr.success else 'FAIL'}",
                old_text="",
                new_text=f"py_compile: {'OK' if cr.success else 'FAIL: ' + cr.error[:100]}",
                citation="py_compile",
                rationale="Python file byte-compiled via py_compile",
            )

        audit.log_edit(
            doc_hash=doc_hash,
            clause_id="test_run",
            clause_label=f"pytest: {test_result.passed} passed, {test_result.failed} failed",
            old_text="",
            new_text=f"pytest: exit={test_result.exit_code}, passed={test_result.passed}, "
            f"failed={test_result.failed}, errors={test_result.errors}",
            citation="pytest",
            rationale="Test suite run via pytest",
        )

        total_edits = len(parse_results) + len(compile_results) + 1
        total_flagged = (
            sum(1 for pr in parse_results if pr.has_errors)
            + sum(1 for cr in compile_results if not cr.success)
            + (1 if not test_ok else 0)
        )

        audit.log_run_completed(
            doc_hash=doc_hash,
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
        )

        audit_log_json = audit.to_json()

        egress_report = generate_zero_egress_report(
            doc_hash=doc_hash,
            playbook_id="code_pipeline",
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
            audit_log_json=audit_log_json,
            private_key=private_key,
        )
        egress_report_json = egress_report.to_json()

    return CodeResult(
        ok=overall_ok,
        parse_results=parse_results,
        compile_results=compile_results,
        test_result=test_result,
        audit_log_json=audit_log_json,
        egress_report_json=egress_report_json,
        doc_hash=doc_hash,
    )
