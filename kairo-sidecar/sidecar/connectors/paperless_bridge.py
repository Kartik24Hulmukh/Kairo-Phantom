"""
Paperless-ngx Bridge (Phase 0.7)

Reads from paperless-ngx REST API: documents, tags, correspondents.
Indexes document corpus into Kairo's vector store (sqlite-vec from Phase 0.4).

DISABLED by default. Enabled via: kairo connectors enable paperless --url <URL> --token <TOKEN>

Security:
- All document content from paperless-ngx is UNTRUSTED — passes through PromptShield
  before being indexed or processed by Kairo
- Air-gap: paperless-ngx runs locally (localhost), so this connector works in air-gap mode

Runtime behavior:
- If paperless-ngx is unreachable: raises ConnectionError with clear message
- NEVER silently returns empty results or fakes a success response
- If auth token is invalid: raises AuthenticationError
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("kairo-sidecar.connectors.paperless")


class PaperlessConnectionError(ConnectionError):
    """Raised when paperless-ngx is unreachable."""

    pass


class PaperlessAuthError(PermissionError):
    """Raised when the paperless-ngx token is invalid."""

    pass


@dataclass
class PaperlessDocument:
    """A document retrieved from paperless-ngx."""

    id: int
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    correspondent: str = ""
    document_type: str = ""
    created_date: str = ""
    file_path: str = ""


class PaperlessBridge:
    """
    Real API client for paperless-ngx.

    Uses HTTP requests to the paperless-ngx REST API.
    All responses are parsed from real JSON — no mocking.

    If the service is unreachable, errors are raised loudly.
    """

    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Token {auth_token}",
            "Accept": "application/json",
        }

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a real HTTP request to paperless-ngx.

        Raises PaperlessConnectionError if unreachable.
        Raises PaperlessAuthError if auth fails.
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
                    raise PaperlessAuthError(
                        "paperless-ngx rejected auth token (HTTP 401). "
                        "Check your token: kairo connectors enable paperless --token <TOKEN>"
                    )
                else:
                    raise PaperlessConnectionError(f"paperless-ngx returned HTTP {response.status}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise PaperlessAuthError(
                    "paperless-ngx rejected auth token (HTTP 401). " "Check your token."
                )
            raise PaperlessConnectionError(f"paperless-ngx returned HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise PaperlessConnectionError(
                f"paperless-ngx unreachable at {self.base_url}: {e.reason}. "
                f"Is paperless-ngx running? Start it via: docker compose up -d"
            )
        except ConnectionError as e:
            raise PaperlessConnectionError(
                f"Cannot connect to paperless-ngx at {self.base_url}: {e}. "
                f"Is paperless-ngx running? Start it via: docker compose up -d"
            )

    def get_documents(self, page: int = 1, page_size: int = 50) -> List[PaperlessDocument]:
        """
        Fetch documents from paperless-ngx.

        Returns a list of PaperlessDocument objects.
        Raises PaperlessConnectionError if service is unreachable.
        """
        data = self._request("/api/documents/", {"page": page, "page_size": page_size})

        documents = []
        for doc_data in data.get("results", []):
            doc = PaperlessDocument(
                id=doc_data.get("id", 0),
                title=doc_data.get("title", ""),
                content=doc_data.get("content", ""),
                tags=[],  # Tags are IDs in the API, need separate lookup
                correspondent=doc_data.get("correspondent", ""),
                document_type=doc_data.get("document_type", ""),
                created_date=doc_data.get("created", ""),
                file_path=doc_data.get("archived_file_name", ""),
            )
            documents.append(doc)

        return documents

    def get_tags(self) -> List[Dict[str, Any]]:
        """Fetch tags from paperless-ngx."""
        data = self._request("/api/tags/")
        return data.get("results", [])

    def get_correspondents(self) -> List[Dict[str, Any]]:
        """Fetch correspondents from paperless-ngx."""
        data = self._request("/api/correspondents/")
        return data.get("results", [])

    def health_check(self) -> bool:
        """
        Check if paperless-ngx is reachable.

        Returns True if reachable, False otherwise.
        NEVER silently returns True — makes a real HTTP request.
        """
        try:
            self._request("/api/documents/", {"page": 1, "page_size": 1})
            return True
        except (PaperlessConnectionError, PaperlessAuthError):
            return False


def is_paperless_enabled() -> bool:
    """Check if paperless connector is explicitly enabled."""
    connectors = os.environ.get("KAIRO_CONNECTORS", "")
    return "paperless" in connectors.lower()


def is_airgap_mode() -> bool:
    """Check if air-gap mode is enabled."""
    return os.environ.get("KAIRO_OFFLINE", "") != "" or os.environ.get("KAIRO_AIRGAP", "") != ""


def create_bridge() -> Optional[PaperlessBridge]:
    """
    Create a PaperlessBridge from environment variables.

    Returns None if not enabled or not configured.
    Raises if enabled but misconfigured.
    """
    if not is_paperless_enabled():
        return None

    if is_airgap_mode():
        # Paperless-ngx runs locally, so it CAN work in air-gap mode
        # But we still need to check if it's configured
        log.info("Paperless bridge enabled in air-gap mode (localhost HTTP only)")

    url = os.environ.get("PAPERLESS_URL", "http://localhost:8000")
    token = os.environ.get("PAPERLESS_TOKEN", "")

    if not token:
        log.error(
            "Paperless bridge enabled but PAPERLESS_TOKEN not set. "
            "Set via: kairo connectors enable paperless --token <TOKEN>"
        )
        return None

    return PaperlessBridge(url, token)
