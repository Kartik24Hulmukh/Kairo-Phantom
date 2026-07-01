"""
Karakeep Bridge (Phase 0.7)

Reads from Karakeep REST API: bookmarks, tags, AI-generated summaries.
Indexes bookmarked web content into Kairo's vector store.

DISABLED by default. Enabled via: kairo connectors enable karakeep --url <URL> --token <TOKEN>

Security:
- All bookmark content from Karakeep is UNTRUSTED — passes through PromptShield
- Air-gap: Karakeep runs locally (localhost), works in air-gap mode

Runtime behavior:
- If Karakeep is unreachable: raises ConnectionError with clear message
- NEVER silently returns empty results or fakes a success response
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("kairo-sidecar.connectors.karakeep")


class KarakeepConnectionError(ConnectionError):
    """Raised when Karakeep is unreachable."""

    pass


class KarakeepAuthError(PermissionError):
    """Raised when the Karakeep token is invalid."""

    pass


@dataclass
class KarakeepBookmark:
    """A bookmark retrieved from Karakeep."""

    id: str
    title: str
    url: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    content: str = ""
    summary: str = ""
    created_date: str = ""


class KarakeepBridge:
    """
    Real API client for Karakeep.

    Uses HTTP requests to the Karakeep REST API.
    All responses are parsed from real JSON — no mocking.

    If the service is unreachable, errors are raised loudly.
    """

    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/json",
        }

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a real HTTP request to Karakeep.

        Raises KarakeepConnectionError if unreachable.
        Raises KarakeepAuthError if auth fails.
        """
        import urllib.request
        import urllib.error
        import json as json_module

        url = f"{self.base_url}{endpoint}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        req = urllib.request.Request(url, headers=self._headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return json_module.loads(response.read().decode("utf-8"))
                elif response.status == 401:
                    raise KarakeepAuthError(
                        "Karakeep rejected auth token (HTTP 401). "
                        "Check your token: kairo connectors enable karakeep --token <TOKEN>"
                    )
                else:
                    raise KarakeepConnectionError(f"Karakeep returned HTTP {response.status}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise KarakeepAuthError(
                    "Karakeep rejected auth token (HTTP 401). Check your token."
                )
            raise KarakeepConnectionError(f"Karakeep returned HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise KarakeepConnectionError(
                f"Karakeep unreachable at {self.base_url}: {e.reason}. "
                f"Is Karakeep running? Start it via: docker run karakeep/karakeep"
            )
        except ConnectionError as e:
            raise KarakeepConnectionError(
                f"Cannot connect to Karakeep at {self.base_url}: {e}. "
                f"Is Karakeep running? Start it via: docker run karakeep/karakeep"
            )

    def get_bookmarks(self, page: int = 1, page_size: int = 50) -> List[KarakeepBookmark]:
        """
        Fetch bookmarks from Karakeep.

        Returns a list of KarakeepBookmark objects.
        Raises KarakeepConnectionError if service is unreachable.
        """
        data = self._request("/api/bookmarks", {"page": page, "page_size": page_size})

        bookmarks = []
        for bm_data in data.get("results", data.get("bookmarks", [])):
            bm = KarakeepBookmark(
                id=str(bm_data.get("id", "")),
                title=bm_data.get("title", ""),
                url=bm_data.get("url", ""),
                description=bm_data.get("description", ""),
                tags=bm_data.get("tags", []),
                content=bm_data.get("content", ""),
                summary=bm_data.get("summary", ""),
                created_date=bm_data.get("created_at", ""),
            )
            bookmarks.append(bm)

        return bookmarks

    def get_tags(self) -> List[Dict[str, Any]]:
        """Fetch tags from Karakeep."""
        data = self._request("/api/tags")
        return data.get("results", data.get("tags", []))

    def health_check(self) -> bool:
        """
        Check if Karakeep is reachable.

        Returns True if reachable, False otherwise.
        NEVER silently returns True — makes a real HTTP request.
        """
        try:
            self._request("/api/bookmarks", {"page": 1, "page_size": 1})
            return True
        except (KarakeepConnectionError, KarakeepAuthError):
            return False


def is_karakeep_enabled() -> bool:
    """Check if karakeep connector is explicitly enabled."""
    connectors = os.environ.get("KAIRO_CONNECTORS", "")
    return "karakeep" in connectors.lower()


def create_bridge() -> Optional[KarakeepBridge]:
    """
    Create a KarakeepBridge from environment variables.

    Returns None if not enabled or not configured.
    """
    if not is_karakeep_enabled():
        return None

    url = os.environ.get("KARAKEEP_URL", "http://localhost:3000")
    token = os.environ.get("KARAKEEP_TOKEN", "")

    if not token:
        log.error(
            "Karakeep bridge enabled but KARAKEEP_TOKEN not set. "
            "Set via: kairo connectors enable karakeep --token <TOKEN>"
        )
        return None

    return KarakeepBridge(url, token)
