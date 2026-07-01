"""
sidecar/secret_gate.py — Gitleaks-style secret detection gate.
Scans source files for hardcoded credentials, API keys, tokens, and PII.
Returns structured findings with file path, line number, and pattern name.
Used in CI to block commits containing secrets.
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger("kairo.secret_gate")

# Patterns that identify secrets. Each is (name, regex, risk_level).
# risk_level: "CRITICAL" blocks CI immediately; "HIGH" is a warning that also blocks.
SECRET_PATTERNS = [
    # Cloud provider secrets
    ("AWS_ACCESS_KEY", r"AKIA[0-9A-Z]{16}", "CRITICAL"),
    (
        "AWS_SECRET_KEY",
        r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*=\s*['\"]?[A-Za-z0-9/+=]{40}",
        "CRITICAL",
    ),
    ("GCP_SERVICE_ACCOUNT", r'"type":\s*"service_account"', "HIGH"),
    (
        "AZURE_CLIENT_SECRET",
        r"(?i)azure[_\-]?client[_\-]?secret\s*=\s*['\"]?[A-Za-z0-9\-_~.]{32,}",
        "CRITICAL",
    ),
    # API keys & tokens
    ("OPENAI_API_KEY", r"sk-[a-zA-Z0-9]{32,}", "CRITICAL"),
    ("OPENAI_PROJECT_KEY", r"sk-proj-[a-zA-Z0-9\-_]{20,}", "CRITICAL"),
    ("ANTHROPIC_API_KEY", r"sk-ant-[a-zA-Z0-9\-_]{64,}", "CRITICAL"),
    ("GITHUB_TOKEN", r"ghp_[A-Za-z0-9]{36}", "CRITICAL"),
    ("GITHUB_OAUTH_TOKEN", r"gho_[A-Za-z0-9]{36}", "CRITICAL"),
    ("GITHUB_APP_TOKEN", r"(ghs|ghu)_[A-Za-z0-9]{36}", "CRITICAL"),
    ("SLACK_TOKEN", r"xox[baprs]-[A-Za-z0-9\-]{10,}", "HIGH"),
    ("STRIPE_SECRET_KEY", r"sk_live_[A-Za-z0-9]{24,}", "CRITICAL"),
    # Generic high-entropy credential patterns
    ("HARDCODED_PASSWORD", r"(?i)password\s*=\s*['\"][^'\"]{8,}['\"]", "HIGH"),
    ("HARDCODED_SECRET", r"(?i)(secret|token|api_key)\s*=\s*['\"][^'\"]{16,}['\"]", "HIGH"),
    ("PRIVATE_KEY_BLOCK", r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----", "CRITICAL"),
    ("DATABASE_URL_WITH_CREDS", r"(?i)(postgres|mysql|mongodb)://[^:]+:[^@]{8,}@", "CRITICAL"),
    # Kairo-specific dangerous patterns
    ("KAIRO_REAL_API_KEY", r"(?i)llm_api_key\s*=\s*['\"][^'\"]{16,}['\"]", "HIGH"),
]

# Files and directories to always skip (build artifacts, test fixtures, etc.)
SKIP_DIRS = {
    ".git",
    "target",
    ".venv",
    "__pycache__",
    "node_modules",
    ".tox",
    "tests",
    "test",
    "testing",
}
SKIP_FILE_SUFFIXES = (".pyc", ".pyo", ".so", ".dll", ".exe", ".bin")
SKIP_FILES_CONTAINING = ("test_", "mock_", "_test", "_mock", "fixture", ".min.js")


@dataclass
class SecretFinding:
    """A single secret finding with location and severity."""

    file: str
    line: int
    pattern_name: str
    risk_level: str
    matched_prefix: str  # First 8 chars of match for context without leaking full secret


@dataclass
class SecretGateResult:
    """Summary result of a secret gate scan."""

    clean: bool
    total_files_scanned: int
    findings: List[SecretFinding] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.risk_level == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.risk_level == "HIGH")


def _should_skip_file(file_path: str) -> bool:
    """Return True if this file should be excluded from scanning."""
    basename = os.path.basename(file_path)
    if basename.endswith(SKIP_FILE_SUFFIXES):
        return True
    # Skip test/mock files
    basename_lower = basename.lower()
    if any(pattern in basename_lower for pattern in SKIP_FILES_CONTAINING):
        return True
    # Skip the secret_gate itself to avoid self-matching on the pattern definitions
    if basename in ("secret_gate.py", "sbom_gate.py"):
        return True
    return False


def scan_file(file_path: str) -> List[SecretFinding]:
    """Scan a single file for secret patterns. Returns list of findings."""
    findings: List[SecretFinding] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                # Skip comment lines and obvious mock/test lines
                stripped = line.strip()
                if stripped.startswith(("#", "//", "*")) and "mock" in stripped.lower():
                    continue
                if any(
                    w in stripped.lower()
                    for w in ("mock", "example", "placeholder", "todo", "fixme")
                ):
                    continue
                for pattern_name, regex, risk in SECRET_PATTERNS:
                    match = re.search(regex, line)
                    if match:
                        # Truncate match to avoid logging full secret
                        matched_prefix = match.group(0)[:8] + "..."
                        findings.append(
                            SecretFinding(
                                file=file_path,
                                line=line_num,
                                pattern_name=pattern_name,
                                risk_level=risk,
                                matched_prefix=matched_prefix,
                            )
                        )
    except Exception as e:
        log.debug(f"[SecretGate] Could not scan {file_path}: {e}")
    return findings


def scan_directory(
    root_dir: str,
    extensions: Optional[List[str]] = None,
) -> SecretGateResult:
    """
    Scan all files in root_dir for secrets.
    Only scans files with the given extensions (default: common source file types).
    Returns a SecretGateResult with findings and overall clean status.
    """
    if extensions is None:
        extensions = [".py", ".rs", ".toml", ".yaml", ".yml", ".json", ".env", ".sh", ".js", ".ts"]

    all_findings: List[SecretFinding] = []
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Prune skipped directories in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            if not any(filename.endswith(ext) for ext in extensions):
                continue

            file_path = os.path.join(dirpath, filename)
            if _should_skip_file(file_path):
                continue

            files_scanned += 1
            findings = scan_file(file_path)
            all_findings.extend(findings)

    clean = len(all_findings) == 0
    result = SecretGateResult(
        clean=clean,
        total_files_scanned=files_scanned,
        findings=all_findings,
    )

    if not clean:
        for f in all_findings:
            log.error(
                f"[SecretGate] {f.risk_level}: {f.pattern_name} in {f.file}:{f.line} (prefix={f.matched_prefix})"
            )
    else:
        log.info(f"[SecretGate] [OK] Clean: scanned {files_scanned} files, no secrets found.")

    return result


def run_gate(root_dir: str, fail_on_high: bool = True) -> bool:
    """
    CI entrypoint: scans root_dir and returns True if clean, False if secrets found.
    CRITICAL findings always fail. HIGH findings fail if fail_on_high=True (default).
    """
    result = scan_directory(root_dir)
    if result.critical_count > 0:
        log.error(
            f"[SecretGate] [FAIL] BLOCKED: {result.critical_count} CRITICAL finding(s). Fix before commit."
        )
        return False
    if fail_on_high and result.high_count > 0:
        log.error(
            f"[SecretGate] [FAIL] BLOCKED: {result.high_count} HIGH finding(s). Fix before commit."
        )
        return False
    if result.clean:
        log.info(f"[SecretGate] [OK] Clean: {result.total_files_scanned} files scanned.")
    return True
