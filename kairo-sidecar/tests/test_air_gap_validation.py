"""Air-gap and network isolation validation test."""

import os
import sys
import time
import socket
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sidecar.telemetry as telemetry
import sidecar.crash_reporter as crash_reporter
from sidecar.oracles import NetworkSnifferOracle


def test_air_gap_zero_network_leakage():
    # Force offline/air-gapped mode
    with patch.dict(os.environ, {"KAIRO_OFFLINE": "1"}):
        # Patch psutil.net_connections to force fallback to process-only connection tracking

        with patch(
            "psutil.net_connections", side_effect=PermissionError("Forced process-only connections")
        ):
            sniffer = NetworkSnifferOracle()
            sniffer.start()

            # Give sniffer thread a tiny bit of time to spin up
            time.sleep(0.2)

            try:
                # 1. Execute crash reporter manual log under KAIRO_OFFLINE=1
                crash_reporter.write_manual_crash("Air-gap test crash")

                # 2. Execute telemetry recording under KAIRO_OFFLINE=1
                telemetry.record_operation("airgap_test", 10.5)
                telemetry.record_span("airgap_span", 5.0)

                # 3. Perform a loopback network operation (should be ignored by private check)
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.1)
                    s.connect(("127.0.0.1", 9999))
                except Exception:
                    pass
                finally:
                    s.close()

            finally:
                external_ips = sniffer.stop()

        # Assert that zero packets/connections were emitted to external IP addresses
        assert len(external_ips) == 0, f"Leaked connections to external IPs: {external_ips}"
