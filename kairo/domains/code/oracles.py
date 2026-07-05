# PROVENANCE: original | clean-room Code domain oracles per VERIFICATION_ORACLES.md
"""Code domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``compile_test_pass`` — after a code edit, the fixture project:
     (a) parses via tree-sitter with zero ERROR nodes,
     (b) py_compile succeeds for all .py files,
     (c) its pytest suite passes (exit code 0, zero failures).
     KILL-PROOF: introduce a syntax error OR break a test → FAILS.

  2. ``parse_validity`` — tree-sitter AST has zero ERROR nodes for edited files.
     KILL-PROOF: inject malformed syntax → FAILS.

Both oracles are KILL-PROVEN: perturbing the code (syntax error, broken test,
malformed syntax) causes a hard failure.

HONEST DEGRADATION:
  If python/pytest/tree-sitter is not installed, the oracles raise
  ``CodeToolchainUnavailableError`` — they never claim pass without a real run.

SCOPE: V1 is PYTHON ONLY (deterministic, offline, stdlib-only fixture).
Other languages = Experimental (honest label).

All operations are fully offline. No network calls. No LLM. No cloud.

Dependencies (all permissive — MIT):
  - tree-sitter (MIT) — incremental parsing
  - tree-sitter-python (MIT) — Python grammar
  - pytest (MIT) — test runner
"""

from __future__ import annotations

from pathlib import Path

from kairo.domains.code.engine import (
    compile_file,
    parse_file,
    run_tests,
)


# ---------------------------------------------------------------------------
# Oracle 1: compile_test_pass
# ---------------------------------------------------------------------------


def compile_test_pass(
    project_dir: str,
    files_to_check: list[str] | None = None,
) -> bool:
    """Oracle: after a code edit, verify parse + compile + test all pass.

    The fixture project must:
      (a) parse via tree-sitter with zero ERROR nodes,
      (b) py_compile succeeds for all .py files,
      (c) its pytest suite passes (exit code 0, zero failures).

    KILL-PROOF: introduce a syntax error OR break a test → oracle FAILS.

    Args:
        project_dir: Path to the project directory.
        files_to_check: Optional list of specific .py files to parse+compile.
                        If None, all .py files in project_dir are checked.

    Returns:
        True if parse + compile + test all pass.

    Raises:
        AssertionError: If any check fails (kill-proof).
        CodeToolchainUnavailableError: If toolchain is not installed.
    """
    project_path = Path(project_dir).resolve()

    if files_to_check is None:
        py_files = sorted(project_path.rglob("*.py"))
    else:
        py_files = [Path(f).resolve() for f in files_to_check]

    # Check 1: tree-sitter parse (zero ERROR nodes)
    for f in py_files:
        if f.exists() and f.suffix == ".py":
            pr = parse_file(str(f))
            if pr.has_errors:
                raise AssertionError(
                    f"compile_test_pass FAILED: parse errors in {f.name}.\n"
                    f"  Error count: {pr.error_count}\n"
                    f"  Errors: {pr.error_nodes[:5]}"
                )

    # Check 2: py_compile (all files compile)
    for f in py_files:
        if f.exists() and f.suffix == ".py":
            cr = compile_file(str(f))
            if not cr.success:
                raise AssertionError(
                    f"compile_test_pass FAILED: compile error in {f.name}.\n"
                    f"  Error: {cr.error[:200]}"
                )

    # Check 3: pytest (exit code 0, zero failures)
    tr = run_tests(str(project_path))
    if tr.exit_code != 0:
        raise AssertionError(
            f"compile_test_pass FAILED: pytest exit code {tr.exit_code}.\n"
            f"  Passed: {tr.passed}, Failed: {tr.failed}, Errors: {tr.errors}\n"
            f"  Output (last 500 chars): {tr.output[-500:]}"
        )
    if tr.failed > 0 or tr.errors > 0:
        raise AssertionError(
            f"compile_test_pass FAILED: {tr.failed} failures, {tr.errors} errors.\n"
            f"  Output (last 500 chars): {tr.output[-500:]}"
        )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: parse_validity
# ---------------------------------------------------------------------------


def parse_validity(file_path: str) -> bool:
    """Oracle: tree-sitter AST has zero ERROR nodes for the given file.

    KILL-PROOF: inject malformed syntax → FAILS.

    Args:
        file_path: Path to the .py file to check.

    Returns:
        True if the file parses with zero ERROR nodes.

    Raises:
        AssertionError: If the file has ERROR nodes (kill-proof).
        CodeToolchainUnavailableError: If tree-sitter is not installed.
    """
    pr = parse_file(file_path)

    if pr.has_errors:
        raise AssertionError(
            f"parse_validity FAILED: {pr.error_count} ERROR nodes in {Path(file_path).name}.\n"
            f"  Errors: {pr.error_nodes[:5]}"
        )

    return True
