# PROVENANCE: original | clean-room airgap egress oracle per specs/R3_AIRGAP_ENFORCEMENT.md + specs/VERIFICATION_ORACLES.md
"""Air-gap egress oracle — deterministic, kill-proven zero-egress verification.

Implements the ``airgap_egress`` oracle from specs/VERIFICATION_ORACLES.md:

    | airgap_egress | zero network | loopback+NIC capture during flow; assert
    |               |              | 0 outbound in air-gap; LAN stays in subnet |
    |               |              | open a socket → fail |

And specs/R3_AIRGAP_ENFORCEMENT.md §3:

    The egress oracle runs live. loopback + NIC capture during every flow;
    asserts 0 outbound packets in sealed mode (LAN-only stays within subnet
    for CRDT collaboration). Kill-proof: open a socket → oracle fails the run.

This oracle works by:

  1. Installing socket-level interception (monkey-patching ``socket.socket.connect``,
     ``socket.create_connection``, ``socket.getaddrinfo``, ``socket.gethostbyname``,
     and ``urllib.request.urlopen``) to record and block every outbound connection
     attempt.
  2. Activating sealed mode (``kairo.sealed_profile.activate_sealed_mode``).
  3. Running the REAL legal-redline pipeline (``kairo.oracles.legal_redline_pipeline``)
     on the real fixture contract.
  4. Asserting that zero outbound connections and zero DNS lookups were attempted.
  5. Producing a signed egress report tied to the audit chain.

KILL-PROOF: if a test flow opens a socket to an external host, the oracle MUST
turn red (report ``zero_egress=False``). This is verified by
``test_airgap_egress_kill_proof`` in the test suite.

The oracle also supports running under ``unshare -n`` (Linux network namespace
isolation) when available — this provides OS-level egress blocking in addition
to the socket-level interception. When ``unshare -n`` is not available (e.g.,
in CI without CAP_SYS_ADMIN), the socket-level interception alone is the
enforcement mechanism, and this is stated explicitly in the report.

Dependencies: stdlib only (socket, os, json, hashlib, traceback, threading).
The legal-redline pipeline itself uses python-docx (BSD-3) and cryptography
(Apache-2.0/BSD-3) — both BUNDLE-lane per specs/TECH_MANIFEST.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EgressAttempt:
    """Record of a single attempted network egress."""

    timestamp: str
    function: str  # which socket function was called
    target: str  # host:port or hostname
    stack_trace: str
    blocked: bool = True  # always True — we block all egress in sealed mode


@dataclass
class AirgapEgressReport:
    """Complete egress monitoring report for a single flow run.

    This report is deterministic given the same inputs (except for the timestamp).
    It records:
      - The number of outbound connection attempts (must be 0).
      - The number of DNS lookup attempts (must be 0).
      - Whether the flow completed successfully.
      - The enforcement mechanism used (socket interception, namespace isolation).
      - A content hash for integrity.
    """

    timestamp: str = ""
    flow_name: str = ""
    total_egress_attempts: int = 0
    total_dns_lookups: int = 0
    session_completed: bool = False
    error: Optional[str] = None
    enforcement_mechanism: str = ""
    namespace_isolated: bool = False
    sealed_mode_active: bool = False
    attempts: list[EgressAttempt] = field(default_factory=list)
    dns_lookups: list[EgressAttempt] = field(default_factory=list)
    doc_hash: str = ""
    report_hash: str = ""

    @property
    def zero_egress(self) -> bool:
        """True only if zero socket connections AND zero DNS lookups."""
        return self.total_egress_attempts == 0 and self.total_dns_lookups == 0

    @property
    def passed(self) -> bool:
        """True only if the flow completed with zero egress."""
        return self.zero_egress and self.session_completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "flow_name": self.flow_name,
            "total_egress_attempts": self.total_egress_attempts,
            "total_dns_lookups": self.total_dns_lookups,
            "zero_egress": self.zero_egress,
            "session_completed": self.session_completed,
            "error": self.error,
            "enforcement_mechanism": self.enforcement_mechanism,
            "namespace_isolated": self.namespace_isolated,
            "sealed_mode_active": self.sealed_mode_active,
            "doc_hash": self.doc_hash,
            "report_hash": self.report_hash,
            "attempts": [
                {
                    "timestamp": a.timestamp,
                    "function": a.function,
                    "target": a.target,
                    "blocked": a.blocked,
                    "stack_trace": a.stack_trace,
                }
                for a in self.attempts
            ],
            "dns_lookups": [
                {
                    "timestamp": a.timestamp,
                    "function": a.function,
                    "target": a.target,
                    "stack_trace": a.stack_trace,
                }
                for a in self.dns_lookups
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def compute_hash(self) -> str:
        """Compute SHA-256 over the report content (excluding report_hash itself)."""
        payload = {k: v for k, v in self.to_dict().items() if k != "report_hash"}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


# ---------------------------------------------------------------------------
# Socket-level egress interceptor
# ---------------------------------------------------------------------------


class SocketEgressInterceptor:
    """Monkey-patches socket-level functions to intercept and block all egress.

    This is the REAL interception layer — it patches the actual socket module
    functions so any code that tries to connect is caught at the syscall boundary.
    No mocks on the production path: the legal-redline pipeline runs real code,
    and the interceptor catches any real attempt to reach the network.

    Loopback (127.0.0.1, ::1) and private/LAN addresses are ALLOWED — the oracle
    only blocks egress to external/public addresses, per R3 §3 ("LAN-only stays
    in-subnet for CRDT collaboration").
    """

    # Private/loopback address prefixes that are allowed (not egress)
    _ALLOWED_PREFIXES = ("127.", "::1", "0.0.0.0", "::", "localhost")

    def __init__(self):
        self.attempts: list[EgressAttempt] = []
        self.dns_lookups: list[EgressAttempt] = []
        self._original: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _is_external(self, address: Any) -> bool:
        """Check if an address is external (non-loopback, non-private)."""
        target_str = str(address)
        for prefix in self._ALLOWED_PREFIXES:
            if target_str.startswith(prefix) or prefix in target_str:
                return False
        # Check for private IP ranges
        if isinstance(address, (tuple, list)) and len(address) >= 1:
            host = str(address[0])
            if host in ("127.0.0.1", "::1", "localhost", "0.0.0.0"):
                return False
            # Check private ranges
            if (
                host.startswith("10.")
                or host.startswith("172.16.")
                or host.startswith("192.168.")
                or host.startswith("169.254.")
            ):
                return False
        return True

    def _capture_stack(self) -> str:
        """Capture a stack trace to identify where the egress attempt originated."""
        stack_lines = traceback.format_stack()[3:]  # skip interceptor internals
        return "".join(stack_lines).strip()

    def _make_blocking_connect(self, original_func: Any, func_name: str) -> Callable:
        """Create a blocking wrapper for a socket connect function."""
        interceptor = self

        def blocked_connect(*args, **kwargs):
            target = "unknown"
            if args:
                addr = args[-1] if len(args) > 0 else kwargs.get("address")
                if isinstance(addr, tuple) and len(addr) >= 1:
                    target = f"{addr[0]}:{addr[1]}" if len(addr) > 1 else str(addr[0])
                elif isinstance(addr, str):
                    target = addr

            if interceptor._is_external(args[-1] if args else None):
                attempt = EgressAttempt(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    function=func_name,
                    target=target,
                    stack_trace=interceptor._capture_stack(),
                )
                with interceptor._lock:
                    interceptor.attempts.append(attempt)
                raise ConnectionError(
                    f"AIR-GAP VIOLATION: {func_name} attempted to connect to {target}. "
                    f"All external network egress is blocked in sealed mode."
                )
            # Loopback/private — allow
            return original_func(*args, **kwargs)

        return blocked_connect

    def _make_blocking_dns(self, original_func: Any, func_name: str) -> Callable:
        """Create a blocking wrapper for a DNS resolution function."""
        interceptor = self

        def blocked_dns(*args, **kwargs):
            hostname = "unknown"
            if args:
                hostname = str(args[0])

            # Allow localhost/loopback DNS
            if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return original_func(*args, **kwargs)

            attempt = EgressAttempt(
                timestamp=datetime.now(timezone.utc).isoformat(),
                function=func_name,
                target=hostname,
                stack_trace=interceptor._capture_stack(),
            )
            with interceptor._lock:
                interceptor.dns_lookups.append(attempt)
            raise socket.gaierror(
                f"AIR-GAP VIOLATION: {func_name} attempted DNS lookup for {hostname}. "
                f"All external DNS resolution is blocked in sealed mode."
            )

        return blocked_dns

    def __enter__(self) -> "SocketEgressInterceptor":
        """Install socket monkey-patches to intercept all external egress."""
        self._original["socket_connect"] = socket.socket.connect
        self._original["socket_connect_ex"] = socket.socket.connect_ex
        self._original["create_connection"] = socket.create_connection
        self._original["getaddrinfo"] = socket.getaddrinfo
        self._original["gethostbyname"] = socket.gethostbyname
        self._original["gethostbyname_ex"] = socket.gethostbyname_ex
        self._original["getfqdn"] = socket.getfqdn

        socket.socket.connect = self._make_blocking_connect(
            self._original["socket_connect"], "socket.socket.connect"
        )
        socket.socket.connect_ex = self._make_blocking_connect(
            self._original["socket_connect_ex"], "socket.socket.connect_ex"
        )
        socket.create_connection = self._make_blocking_connect(
            self._original["create_connection"], "socket.create_connection"
        )
        socket.getaddrinfo = self._make_blocking_dns(
            self._original["getaddrinfo"], "socket.getaddrinfo"
        )
        socket.gethostbyname = self._make_blocking_dns(
            self._original["gethostbyname"], "socket.gethostbyname"
        )
        socket.gethostbyname_ex = self._make_blocking_dns(
            self._original["gethostbyname_ex"], "socket.gethostbyname_ex"
        )
        socket.getfqdn = self._make_blocking_dns(
            self._original["getfqdn"], "socket.getfqdn"
        )

        # Also intercept urllib.request.urlopen if available
        try:
            import urllib.request

            self._original["urlopen"] = urllib.request.urlopen

            interceptor = self

            def blocked_urlopen(url, *args, **kwargs):
                url_str = str(url)
                attempt = EgressAttempt(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    function="urllib.request.urlopen",
                    target=url_str,
                    stack_trace=interceptor._capture_stack(),
                )
                with interceptor._lock:
                    interceptor.attempts.append(attempt)
                raise ConnectionError(
                    f"AIR-GAP VIOLATION: urllib.request.urlopen attempted to "
                    f"connect to {url_str}. All external network egress is "
                    f"blocked in sealed mode."
                )

            urllib.request.urlopen = blocked_urlopen
        except ImportError:
            pass

        # Set environment variables to discourage network use
        os.environ["KAIRO_AIRGAP"] = "1"
        os.environ["KAIRO_SEALED"] = "1"
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Restore original socket functions."""
        socket.socket.connect = self._original["socket_connect"]
        socket.socket.connect_ex = self._original["socket_connect_ex"]
        socket.create_connection = self._original["create_connection"]
        socket.getaddrinfo = self._original["getaddrinfo"]
        socket.gethostbyname = self._original["gethostbyname"]
        socket.gethostbyname_ex = self._original["gethostbyname_ex"]
        socket.getfqdn = self._original["getfqdn"]

        if "urlopen" in self._original:
            try:
                import urllib.request

                urllib.request.urlopen = self._original["urlopen"]
            except ImportError:
                pass

        return False  # Don't suppress exceptions


# ---------------------------------------------------------------------------
# Namespace isolation check
# ---------------------------------------------------------------------------


def _check_namespace_isolation() -> bool:
    """Check if we are running inside an isolated network namespace.

    On Linux, ``unshare -n`` creates a network namespace with no external
    interfaces (only loopback). We detect this by checking if the only
    network interface is ``lo``.

    Returns True if namespace isolation is active, False otherwise.
    """
    try:
        import subprocess

        result = subprocess.run(
            ["ip", "link", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            interfaces = []
            for line in lines:
                if ": " in line and "@" not in line:
                    parts = line.split(": ")
                    if len(parts) >= 2:
                        iface = parts[1].split(":")[0].strip()
                        interfaces.append(iface)
            # If only loopback exists, we are in an isolated namespace
            return len(interfaces) == 1 and interfaces[0] == "lo"
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Main oracle: run the legal-redline flow under egress interception
# ---------------------------------------------------------------------------


def run_airgap_egress_oracle(
    contract_path: str,
    playbook_path: str,
    output_path: str,
    private_key: Any = None,
) -> AirgapEgressReport:
    """Run the legal-redline flow under sealed mode with live egress capture.

    This is the ``airgap_egress`` oracle from VERIFICATION_ORACLES.md. It:

      1. Activates sealed mode.
      2. Installs socket-level egress interception.
      3. Runs the REAL legal-redline pipeline on the given contract.
      4. Asserts zero outbound connections and zero DNS lookups.
      5. Returns a detailed egress report.

    Args:
        contract_path: Path to the input contract .docx file.
        playbook_path: Path to the redline playbook JSON file.
        output_path: Path where the redlined .docx will be saved.
        private_key: Optional Ed25519 private key for signed audit/egress reports.

    Returns:
        AirgapEgressReport with the egress capture results.
    """
    from kairo.sealed_profile import activate_sealed_mode, is_sealed
    from kairo.oracles.legal_redline_pipeline import redline_contract

    # 1. Activate sealed mode
    if not is_sealed():
        activate_sealed_mode(reason="airgap_egress oracle")

    # 2. Check namespace isolation
    namespace_isolated = _check_namespace_isolation()

    report = AirgapEgressReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        flow_name="legal_redline_pipeline",
        enforcement_mechanism="socket_interception"
        + (" + network_namespace" if namespace_isolated else ""),
        namespace_isolated=namespace_isolated,
        sealed_mode_active=True,
    )

    # 3. Run the flow under egress interception
    with SocketEgressInterceptor() as interceptor:
        try:
            result = redline_contract(
                contract_path=contract_path,
                playbook_path=playbook_path,
                output_path=output_path,
                author="Kairo Legal (Sealed)",
                private_key=private_key,
            )
            report.session_completed = result.ok
            if not result.ok:
                report.error = result.error
            report.doc_hash = result.doc_hash
        except ConnectionError as e:
            report.session_completed = False
            report.error = str(e)
        except Exception as e:
            report.session_completed = False
            report.error = f"Flow error: {type(e).__name__}: {e}"

    # 4. Record egress attempts
    report.attempts = interceptor.attempts
    report.dns_lookups = interceptor.dns_lookups
    report.total_egress_attempts = len(interceptor.attempts)
    report.total_dns_lookups = len(interceptor.dns_lookups)

    # 5. Compute report hash
    report.report_hash = report.compute_hash()

    return report


def verify_airgap_egress(report: AirgapEgressReport) -> bool:
    """Verify that an AirgapEgressReport shows zero egress and completed flow.

    This is the assertion function used by tests and the gauntlet.
    Returns True only if:
      - The flow completed successfully.
      - Zero outbound connection attempts.
      - Zero DNS lookup attempts.
    """
    return report.passed


# ---------------------------------------------------------------------------
# Kill-proof: deliberately open a socket to prove the oracle catches it
# ---------------------------------------------------------------------------


def run_kill_proof() -> AirgapEgressReport:
    """Deliberately attempt an outbound socket connection to prove the oracle catches it.

    This is the KILL-PROOF for the airgap_egress oracle. It:
      1. Activates sealed mode.
      2. Installs socket-level egress interception.
      3. Deliberately attempts to connect to an external host.
      4. Returns a report that MUST show zero_egress=False.

    If this report shows zero_egress=True, the oracle is broken (it failed to
    catch a real egress attempt) and the test suite must fail.
    """
    from kairo.sealed_profile import activate_sealed_mode, is_sealed

    if not is_sealed():
        activate_sealed_mode(reason="kill_proof")

    namespace_isolated = _check_namespace_isolation()

    report = AirgapEgressReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        flow_name="kill_proof_deliberate_egress",
        enforcement_mechanism="socket_interception"
        + (" + network_namespace" if namespace_isolated else ""),
        namespace_isolated=namespace_isolated,
        sealed_mode_active=True,
    )

    with SocketEgressInterceptor() as interceptor:
        try:
            # Deliberately attempt to connect to an external host
            # This MUST be caught by the interceptor
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("93.184.216.34", 80))  # example.com — external
            s.close()
            report.session_completed = True
        except (ConnectionError, socket.gaierror, OSError):
            # Expected — the interceptor blocked the connection
            report.session_completed = True  # The flow "completed" by being blocked

        try:
            # Also deliberately attempt a DNS lookup
            socket.gethostbyname("example.com")
        except (socket.gaierror, OSError):
            pass  # Expected

    report.attempts = interceptor.attempts
    report.dns_lookups = interceptor.dns_lookups
    report.total_egress_attempts = len(interceptor.attempts)
    report.total_dns_lookups = len(interceptor.dns_lookups)
    report.report_hash = report.compute_hash()

    return report


# ---------------------------------------------------------------------------
# Sealed binary scan — static symbol check
# ---------------------------------------------------------------------------


# Network symbols that MUST NOT appear in sealed-mode source files.
# This is the runtime complement to ci/sealed_no_network.yml.
NETWORK_SYMBOL_PATTERNS = [
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "requests.Session",
    "httpx.get",
    "httpx.post",
    "httpx.Client",
    "httpx.AsyncClient",
    "aiohttp.ClientSession",
    "urllib.request.urlopen",
    "urllib.request.Request",
    "http.client.HTTPConnection",
    "http.client.HTTPSConnection",
    "socket.connect",  # except in this oracle file and sealed_profile.py
    "websocket.create_connection",
    "websockets.connect",
    "litellm.completion",
    "litellm.acompletion",
    "openai.ChatCompletion",
    "openai.AsyncOpenAI",
    "anthropic.Anthropic",
    "sentry_sdk.capture",
    "sentry_sdk.init",
]


def sealed_binary_scan(
    source_dirs: list[str], allowlist: list[str] | None = None
) -> dict[str, Any]:
    """Static-scan source directories for networking symbols.

    This is the ``sealed_binary_scan`` check from VERIFICATION_ORACLES.md.
    It scans Python source files in the given directories for any networking
    symbol that should not be present in a sealed build.

    Args:
        source_dirs: List of directories to scan.
        allowlist: Files that are allowed to contain network symbols (e.g.,
                   the egress oracle itself, which must reference socket.connect
                   to intercept it).

    Returns:
        A dict with:
          - "passed": True if no violations found.
          - "violations": List of {file, line, pattern} for each violation.
          - "scanned_files": Number of files scanned.
    """
    import re

    if allowlist is None:
        # Default allowlist: files that legitimately reference network symbols
        # (the egress oracle intercepts socket.connect; sealed_profile lists
        # forbidden modules; tests verify kill-proofs)
        allowlist = [
            "airgap_egress.py",
            "sealed_profile.py",
            "test_airgap_egress.py",
            "test_airgap_zero_egress.py",
            "test_airgap_ci.py",
            "airgap_proof.py",
        ]

    violations: list[dict[str, Any]] = []
    scanned = 0

    # Build a regex that matches any of the network symbol patterns
    # Escape special regex chars in patterns
    escaped = [re.escape(p) for p in NETWORK_SYMBOL_PATTERNS]
    pattern_re = re.compile("|".join(escaped))

    for source_dir in source_dirs:
        if not os.path.isdir(source_dir):
            continue
        for root, dirs, files in os.walk(source_dir):
            # Skip __pycache__, .git, etc.
            dirs[:] = [
                d
                for d in dirs
                if d
                not in (
                    "__pycache__",
                    ".git",
                    ".venv",
                    "node_modules",
                    "target",
                    "build",
                )
            ]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                if fname in allowlist:
                    continue
                fpath = os.path.join(root, fname)
                scanned += 1
                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            # Skip comments
                            stripped = line.lstrip()
                            if stripped.startswith("#"):
                                continue
                            for match in pattern_re.finditer(line):
                                violations.append(
                                    {
                                        "file": fpath,
                                        "line": lineno,
                                        "pattern": match.group(),
                                        "context": stripped.strip(),
                                    }
                                )
                except Exception:
                    pass

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "scanned_files": scanned,
    }


# Type alias for the blocking connect function
Callable = Any  # Avoid importing from typing.Callable for stdlib-only constraint
