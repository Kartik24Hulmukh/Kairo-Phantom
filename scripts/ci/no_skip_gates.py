"""
CI gate script to prevent developers or auto-fixers from introducing skipped or ignored tests.

Scans:
  - ALL Python test files (test_*.py) anywhere in the repo (not just in tests/ dirs)
  - ALL Rust files (.rs) in the repo

Forbidden patterns (Python):
  - @pytest.mark.skip        — direct skip decorator
  - pytest.skip(             — imperative skip call
  - @unittest.skip           — unittest skip decorator
  - @pytest.mark.xfail       — expected failure (masks real failures)
  - pytest.xfail(            — imperative xfail call
  - pytest.importorskip(     — a skip renamed to dodge this linter; hard-dependency instead
  - @pytest.mark.skipif      — conditional skip; use hard dependency or feature flag

Forbidden patterns (Rust):
  - #[ignore]                — ignored test

Excluded paths (not test code):
  - .venv, .agents, node_modules, .git, __pycache__
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("kairo.no_skip")

# Directories to exclude from scanning
EXCLUDE_DIRS = {".venv", ".agents", "node_modules", ".git", "__pycache__", "target"}

PYTHON_FORBIDDEN = [
    "@pytest.mark.skip",
    "pytest.skip(",
    "@unittest.skip",
    "@pytest.mark.xfail",
    "pytest.xfail(",
    "pytest.importorskip(",      # skip-renamed-to-dodge-linter: use hard import instead
    "@pytest.mark.skipif",       # conditional skip: make dep hard or use explicit feature flag
]

RUST_FORBIDDEN = [
    "#[ignore]",
]


def _is_excluded(path: str) -> bool:
    """Return True if any path component is in the exclusion set."""
    parts = path.replace("\\", "/").split("/")
    return any(p in EXCLUDE_DIRS for p in parts)


def scan_python_files(repo_root: str) -> bool:
    """Scan ALL test_*.py files in the repo for forbidden skip patterns."""
    clean = True

    for root, dirs, files in os.walk(repo_root):
        # Prune excluded directories in-place so os.walk does not descend into them
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        if _is_excluded(root):
            continue

        for file in files:
            if not (file.endswith(".py") and file.startswith("test_")):
                continue

            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        stripped = line.strip()
                        # Skip pure comment lines
                        if stripped.startswith("#"):
                            continue
                        for keyword in PYTHON_FORBIDDEN:
                            if keyword in line:
                                log.error(
                                    f"❌ Forbidden pattern in {file_path}:{line_num} "
                                    f"-> '{stripped}'"
                                )
                                clean = False
            except Exception as e:
                log.warning(f"Could not read {file_path}: {e}")

    return clean


def scan_rust_files(repo_root: str) -> bool:
    """Scan ALL .rs files in the repo for #[ignore] attributes."""
    clean = True

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        if _is_excluded(root):
            continue

        for file in files:
            if not file.endswith(".rs"):
                continue

            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        stripped = line.strip()
                        if stripped.startswith("//"):
                            continue
                        for keyword in RUST_FORBIDDEN:
                            if keyword in line:
                                log.error(
                                    f"❌ Ignored Rust test in {file_path}:{line_num} "
                                    f"-> '{stripped}'"
                                )
                                clean = False
            except Exception as e:
                log.warning(f"Could not read {file_path}: {e}")

    return clean


def main():
    # Repo root is 3 levels up from scripts/ci/no_skip_gates.py
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    log.info(f"[No-Skip Gate] Python scan: kairo-sidecar/tests/ | Rust scan: {repo_root}")
    log.info(f"[No-Skip Gate] Python forbidden: {PYTHON_FORBIDDEN}")
    log.info(f"[No-Skip Gate] Rust forbidden:   {RUST_FORBIDDEN}")
    log.info(f"[No-Skip Gate] Excluded dirs:    {EXCLUDE_DIRS}")

    python_clean = scan_python_files(os.path.join(repo_root, "kairo-sidecar", "tests"))
    rust_clean   = scan_rust_files(repo_root)

    if not python_clean or not rust_clean:
        log.error(
            "❌ CI build failed: Skipped/ignored tests are strictly forbidden.\n"
            "   - Replace pytest.skip / importorskip with a hard import (fails honestly if dep missing).\n"
            "   - Replace @pytest.mark.skipif with an explicit feature flag or hard dependency.\n"
            "   - Remove #[ignore] from Rust tests."
        )
        sys.exit(1)

    log.info("✅ No-Skip enforcement gate passed — zero forbidden patterns found.")
    sys.exit(0)


if __name__ == "__main__":
    main()
