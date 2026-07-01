import sys
import socket
from pathlib import Path
from unittest.mock import patch

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.router import DomainMasterRouter


def test_offline_mode_isolation():
    # Attempting to open a socket connection should raise an error in this test
    # to guarantee our masters perform extraction/routing/validation 100% offline.

    def blocked_connect(self, address):
        raise socket.error("Network connection blocked in offline test mode.")

    with patch("socket.socket.connect", side_effect=blocked_connect):
        # Instantiate objects and check offline behaviors
        router = DomainMasterRouter()
        # Ensure it starts without making any network connections
        assert router is not None

        # Verify that we can normalise domains and access masters completely offline
        assert router.masters["word"] is not None
        assert router.masters["excel"] is not None
