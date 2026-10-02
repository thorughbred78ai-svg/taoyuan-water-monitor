from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from config import HTTP_TIMEOUT, USER_AGENT


class WRAClient:
    """HTTP client for WRA APIs with diagnostic logging."""

    def __init__(
        self,
        timeout: int = HTTP_TIMEOUT,
    ) -> None:
        self.timeout = timeout

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        })

    @staticmethod
    def _write_json(
        path: Path,
        data: Any,
    ) -> None:
        """Write UTF-8 JSON."""

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_text(
        path: Path,
        text: str,
    ) -> None:
        """Write UTF-8 text."""

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            text,
            encoding="utf-8",
        )

    @staticmethod
    def _headers_to_dict(
        headers: Any,
    ) -> dict[str, str]:
        """Convert HTTP headers to a normal dictionary."""

        return {
            str(key): str(value)
            for key, value in headers.items()
        }

    def get(
        self,
        url: str,
        output_file: Path,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Perform a GET request.

        The exact prepared URL and response information
        are printed for WRA API diagnostics.
        """

        print()
        print("=" * 70)
        print("[WRA] HTTP REQUEST")
        print("=" * 70)

        print(
            "[WRA] METHOD:",
            "GET",
        )

        print(
            "[WRA] URL:",
            url,
        )

        print(
            "[WRA] PARAMS:",
            json.dumps(
                params,
                ensure_ascii=False,
                indent=2,
            ),
        )

        print(
            "[WRA] OUTPUT:",
            output_file,
        )

        # ==================================================
        # Build PreparedRequest
        # ==================================================

        request = requests.Request(
            method="GET",
            url=url,
            params=params,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
            },
        )

        try:
            prepared = self.session.prepare_request(
                request
            )

        except requests.RequestException as exc:
            print()
            print("=" * 70)
            print("[WRA] PREPARE REQUEST FAILED")
            print("=" * 70)

            print(
                "[WRA] exception:",
                repr(exc),
            )

            raise RuntimeError(
                f"Failed to prepare WRA request: {exc}"
            ) from exc

        # ==================================================
        # Prepared request diagnostics
        # ==================================================

        print()
        print("=" * 70)
        print("[WRA] PREPARED REQUEST")
        print("=" * 70)

        print(
            "[WRA] PREPARED METHOD:",
            prepared.method,
        )

        print(
            "[WRA] PREPARED URL:",
            prepared.url,
        )

        if "?" in prepared.url:
            prepared_query = prepared.url.split(
                "?",
                1,
            )[1]
        else:
            prepared_query = "(none)"

        print(
            "[WRA] PREPARED QUERY:",
            prepared_query,
        )

        print(
            "[WRA] PREPARED HEADERS:",
            json.dumps(
                dict(prepared.headers),
                ensure_ascii=False,
                indent=2,
            ),
        )

        # ==================================================
        # Send request
        # ==================================================

        try:
            response = self.session.send(
                prepared,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:
            print()
            print("=" * 70)
            print("[WRA] REQUEST EXCEPTION")
            print("=" * 70)

            print(
                "[WRA] exception:",
                repr(exc),
            )

            raise RuntimeError(
                "WRA HTTP request failed: "
                f"{exc}"
            ) from exc

        # ==================================================
        # Response diagnostics
        # ==================================================

        print()
        print("=" * 70)
        print("[WRA] HTTP RESPONSE")
        print("=" * 70)

        print(
            "[WRA] RESPONSE URL:",
            response.url,
        )

        print(
            "[WRA] STATUS:",
            response.status_code,
        )

        print(
            "[WRA] REASON:",
            response.reason,
        )

        print(
            "[WRA] OK:",
            response.ok,
        )

        print(
            "[WRA] CONTENT-TYPE:",
            response.headers.get(
                "Content-Type"
            ),
        )

        print(
            "[WRA] CONTENT-LENGTH HEADER:",
            response.headers.get(
                "Content-Length"
            ),
        )

        print(
            "[WRA] RESPONSE SIZE:",
            len(response.content),
            "bytes",
        )

        print(
            "[WRA] RESPONSE HEADERS:",
            json.dumps(
                self._headers_to_dict(
                    response.headers
                ),
                ensure_ascii=False,
                indent=2,
            ),
        )

        # ==================================================
        # Prepare output directory
        # ==================================================

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ==================================================
        # Save response headers
        # ==================================================

        headers_file = output_file.with_suffix(
            output_file.suffix
            + ".headers.json"
        )

        self._write_json(
            headers_file,
            self._headers_to_dict(
                response.headers
            ),
        )

        # ==================================================
        # Error response
        # ==================================================

        if not response.ok:
            print()
            print("=" * 70)
            print("[WRA] ERROR RESPONSE")
            print("=" * 70)

            error_text = response.text

            print(
                error_text[:10000]
            )

            # ----------------------------------------------
            # Save error body
            # ----------------------------------------------

            error_file = output_file.with_suffix(
                output_file.suffix
                + ".error.txt"
            )

            self._write_text(
                error_file,
                error_text,
            )

            print(
                "[WRA] ERROR FILE:",
                error_file,
            )

            # ----------------------------------------------
            # Save JSON error if possible
            # ----------------------------------------------

            error_json = None

            try:
                error_json = response.json()

            except ValueError:
                error_json = None

            if error_json is not None:
                error_json_file = output_file.with_suffix(
                    output_file.suffix
                    + ".error.json"
                )

                self._write_json(
                    error_json_file,
                    error_json,
                )

                print(
                    "[WRA] ERROR JSON FILE:",
                    error_json_file,
                )

            # ----------------------------------------------
            # Raise exception
            # ----------------------------------------------

            raise RuntimeError(
                "WRA API request failed: "
                f"HTTP {response.status_code}\n"
                f"Reason: {response.reason}\n"
                f"Prepared URL: {prepared.url}\n"
                f"Response URL: {response.url}\n"
                f"Response: {error_text[:5000]}"
            )

        # ==================================================
        # Successful response
        # ==================================================

        print()
        print(
            "[WRA] HTTP request succeeded."
        )

        output_file.write_bytes(
            response.content
        )

        print(
            "[WRA] BODY FILE:",
            output_file,
        )

        # ==================================================
        # Raster metadata
        # ==================================================

        metadata_raw = (
            response.headers.get("RasterMapMetaData")
            or response.headers.get("RasterMepMetaData")
        )

        metadata_file = output_file.with_suffix(
            output_file.suffix
            + ".metadata.json"
        )

        metadata = None

        if metadata_raw:
            print(
                "[WRA] RasterMapMetaData found."
            )

            try:
                metadata = json.loads(
                    metadata_raw
                )

                self._write_json(
                    metadata_file,
                    metadata,
                )

                print(
                    "[WRA] METADATA FILE:",
                    metadata_file,
                )

            except json.JSONDecodeError:
                print(
                    "[WRA] RasterMapMetaData "
                    "is not valid JSON."
                )

                self._write_text(
                    metadata_file,
                    metadata_raw,
                )

                metadata = metadata_raw

                print(
                    "[WRA] RAW METADATA FILE:",
                    metadata_file,
                )

        else:
            print(
                "[WRA] RasterMepMetaData "
                "header not found."
            )

        # ==================================================
        # Return diagnostic result
        # ==================================================

        return {
            "url": response.url,
            "prepared_url": prepared.url,
            "method": prepared.method,
            "params": params,
            "status_code": response.status_code,
            "reason": response.reason,
            "ok": response.ok,
            "content_type": response.headers.get(
                "Content-Type"
            ),
            "content_length": len(
                response.content
            ),
            "metadata": metadata,
            "body_file": str(
                output_file
            ),
            "headers_file": str(
                headers_file
            ),
        }
