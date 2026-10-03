from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import CWA_URL, HTTP_RETRIES, HTTP_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)


class CWAError(RuntimeError):
    pass


def redact(text: str, key: str) -> str:
    """Remove the API key (raw and URL-encoded) from any text before logging/storing."""
    if not key:
        return text
    return text.replace(key, "***").replace(quote(key, safe=""), "***")


def fetch_rain_stations(api_key: str) -> dict[str, Any]:
    """GET O-A0002-001 (all stations). The key is never logged or written to disk."""
    if not api_key:
        raise CWAError("CWA_API_KEY is not set.")

    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=HTTP_RETRIES, backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )))
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    log.info("GET %s (all stations)", CWA_URL)  # 不記錄 query（含授權碼）
    try:
        resp = session.get(
            CWA_URL,
            params={"Authorization": api_key, "format": "JSON"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise CWAError(redact(f"CWA request failed: {exc}", api_key)) from None

    log.info("CWA HTTP %s size=%d", resp.status_code, len(resp.content))
    if not resp.ok:
        raise CWAError(redact(f"HTTP {resp.status_code} {resp.reason}: {resp.text[:300]}", api_key))
    try:
        payload = resp.json()
    except ValueError:
        raise CWAError("CWA response is not JSON.") from None
    if str(payload.get("success", "true")).lower() != "true":
        raise CWAError(redact(f"CWA success=false: {str(payload)[:300]}", api_key))
    return payload
