
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import HTTP_RETRIES, HTTP_TIMEOUT, USER_AGENT
from utils import save_json

log = logging.getLogger(__name__)


class WRAError(RuntimeError):
    pass


class WRAClient:
    """HTTP client for WRA open APIs (retry + diagnostics, no secrets logged)."""

    def __init__(self) -> None:
        retry = Retry(
            total=HTTP_RETRIES,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})

    def get(
        self,
        url: str,
        output_file: Path,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        log.info("GET %s params=%s", url, params)

        try:
            resp = self.session.get(url, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise WRAError(f"WRA request failed: {exc}") from exc

        log.info(
            "HTTP %s type=%s size=%d",
            resp.status_code,
            resp.headers.get("Content-Type"),
            len(resp.content),
        )

        save_json(
            output_file.with_name(output_file.name + ".headers.json"),
            {str(k): str(v) for k, v in resp.headers.items()},
        )

        if not resp.ok:
            err = output_file.with_name(output_file.name + ".error.txt")
            err.write_text(resp.text, encoding="utf-8")
            raise WRAError(
                f"HTTP {resp.status_code} {resp.reason} for {resp.url}: {resp.text[:500]}"
            )

        output_file.write_bytes(resp.content)

        raw_meta = resp.headers.get("RasterMapMetaData") or resp.headers.get(
            "RasterMepMetaData"  # 官方 header 曾出現此拼字
        )
        metadata: Any = None
        if raw_meta:
            try:
                metadata = json.loads(raw_meta)
            except json.JSONDecodeError:
                log.warning("RasterMapMetaData is not valid JSON")
                metadata = {"raw": raw_meta}
            save_json(output_file.with_name(output_file.name + ".metadata.json"), metadata)

        return {
            "url": resp.url,
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type"),
            "content_length": len(resp.content),
            "metadata": metadata,
            "body_file": output_file.name,
        }
