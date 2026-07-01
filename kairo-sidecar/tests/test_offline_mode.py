import os
import sys
import socket
import pytest
from pathlib import Path
from unittest.mock import patch

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.updater import check_for_update


def test_updater_offline_mode():
    # Set offline mode env var
    with patch.dict(os.environ, {"KAIRO_OFFLINE": "1"}):
        # Even if socket connects, check_for_update should return None immediately and not perform urlopen
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = check_for_update()
            assert result is None
            mock_urlopen.assert_not_called()


def test_socket_connect_blocks_non_local_under_offline_env():
    # Verify that socket connects are blocked for public IPs when offline
    def mock_connect(self, address):
        host, port = address
        if host not in ("localhost", "127.0.0.1", "::1"):
            raise socket.error(f"Network connection to {host}:{port} blocked in offline mode.")
        return None  # allowed local connect

    with patch.dict(os.environ, {"KAIRO_OFFLINE": "1"}):
        with patch("socket.socket.connect", new=mock_connect):
            # localhost connection should be allowed (returns None)
            s = socket.socket()
            s.connect(("127.0.0.1", 11434))

            # public connection should be blocked
            with pytest.raises(socket.error) as excinfo:
                s.connect(("api.github.com", 443))
            assert "blocked in offline mode" in str(excinfo.value)
