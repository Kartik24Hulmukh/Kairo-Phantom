"""
Risk A4: Repo Size → Contributor Barrier.
Test: repo must be <500MB for clean clone. CI guard fails if exceeded.
"""

import subprocess
from pathlib import Path


class TestRepoSize:
    """Repo must stay under 500MB for contributor accessibility."""

    def test_repo_size_under_500mb(self):
        """The working tree (excluding .git) must be under 500MB."""
        repo_root = Path(__file__).resolve().parent.parent
        # Use du to measure (exclude .git, target, node_modules, __pycache__)
        result = subprocess.run(
            [
                "du",
                "-sh",
                "--exclude=.git",
                "--exclude=target",
                "--exclude=node_modules",
                "--exclude=__pycache__",
                "--exclude=.cache",
                str(repo_root),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"du failed: {result.stderr}"
        # Parse size (e.g., "94M\t/path")
        size_str = result.stdout.split()[0]
        # Convert to MB
        if size_str.endswith("G"):
            size_mb = float(size_str[:-1]) * 1024
        elif size_str.endswith("M"):
            size_mb = float(size_str[:-1])
        elif size_str.endswith("K"):
            size_mb = float(size_str[:-1]) / 1024
        else:
            size_mb = float(size_str)

        assert (
            size_mb < 500
        ), f"Repo size {size_mb:.1f}MB exceeds 500MB limit — contributor barrier risk"

    def test_no_large_files_in_git_tracking(self):
        """No tracked file should be larger than 10MB (except model artifacts)."""
        repo_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            ["git", "ls-files", "--max-size=10M"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        # git ls-files --max-size is not a standard flag; use find instead
        result = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, cwd=str(repo_root), timeout=10
        )
        large_files = []
        for filepath in result.stdout.strip().splitlines():
            full_path = repo_root / filepath
            if full_path.exists():
                size = full_path.stat().st_size
                if size > 10 * 1024 * 1024:  # 10MB
                    # Allow model artifacts and fixtures
                    if not any(ext in filepath for ext in [".gguf", ".onnx", ".pt", ".bin"]):
                        large_files.append(f"{filepath}: {size / 1024 / 1024:.1f}MB")

        assert len(large_files) == 0, f"Files >10MB in git (not model artifacts): {large_files}"

    def test_gitignore_covers_build_artifacts(self):
        """.gitignore must cover target/, node_modules/, __pycache__/."""
        repo_root = Path(__file__).resolve().parent.parent
        gitignore = (repo_root / ".gitignore").read_text()
        assert "target" in gitignore, ".gitignore missing target/"
        assert "node_modules" in gitignore, ".gitignore missing node_modules/"
        assert "__pycache__" in gitignore, ".gitignore missing __pycache__/"
