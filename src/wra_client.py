from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from config import HTTP_TIMEOUT, USER_AGENT


class WRAClient:

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


    def get(
        self,
        url: str,
        output_file: Path,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        print()
        print("=" * 70)
        print("[WRA] HTTP REQUEST")
        print("=" * 70)

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


        # ==================================================
        # Build PreparedRequest first
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

        prepared = self.session.prepare_request(
            request
        )


        print(
            "[WRA] PREPARED URL:",
            prepared.url,
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
            print(
                "[WRA] REQUEST EXCEPTION:"
            )

            print(
                repr(exc)
            )

            raise RuntimeError(
                f"WRA request failed: {exc}"
            ) from exc


        # ==================================================
        # Response information
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
            "[WRA] CONTENT-TYPE:",
            response.headers.get(
                "Content-Type"
            ),
        )

        print(
            "[WRA] CONTENT-LENGTH:",
            response.headers.get(
                "Content-Length"
            ),
        )

        print(
            "[WRA] RESPONSE SIZE:",
            len(response.content),
            "bytes",
        )


        # ==================================================
        # Prepare output directory
        # ==================================================

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )


        # ==================================================
        # Save headers
        # ==================================================

        headers_file = (
            output_file.with_suffix(
                output_file.suffix
                + ".headers.json"
            )
        )

        headers = {
            key: value
            for key, value
            in response.headers.items()
        }

        headers_file.write_text(
            json.dumps(
                headers,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


        # ==================================================
        # Error response
        # ==================================================

        if not response.ok:

            print()
            print("=" * 70)
            print("[WRA] ERROR RESPONSE")
            print("=" * 70)

            print(
                response.text[:10000]
            )


            error_file = (
                output_file.with_suffix(
                    output_file.suffix
                    + ".error.txt"
                )
            )

            error_file.write_text(
                response.text,
                encoding="utf-8",
            )


            try:

                error_json = response.json()

                error_json_file = (
                    output_file.with_suffix(
                        output_file.suffix
                        + ".error.json"
                    )
                )

                error_json_file.write_text(
                    json.dumps(
                        error_json,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            except ValueError:

                pass


            raise RuntimeError(
                "WRA API request failed: "
                f"HTTP {response.status_code}\n"
                f"URL: {response.url}\n"
                f"Response: "
                f"{response.text[:5000]}"
            )


        # ==================================================
        # Save successful response
        # ==================================================

        output_file.write_bytes(
            response.content
        )


        # ==================================================
        # Raster metadata
        # ==================================================

        metadata_raw = (
            response.headers.get(
                "RasterMepMetaData"
            )
        )

        metadata_file = (
            output_file.with_suffix(
                output_file.suffix
                + ".metadata.json"
            )
        )

        metadata = None


        if metadata_raw:

            print(
                "[WRA] RasterMepMetaData found."
            )

            try:

                metadata = json.loads(
                    metadata_raw
                )

                metadata_file.write_text(
                    json.dumps(
                        metadata,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            except json.JSONDecodeError:

                metadata_file.write_text(
                    metadata_raw,
                    encoding="utf-8",
                )

                metadata = metadata_raw

        else:

            print(
                "[WRA] RasterMepMetaData "
                "header not found."
            )


        return {

            "url":
                response.url,

            "status_code":
                response.status_code,

            "content_type":
                response.headers.get(
                    "Content-Type"
                ),

            "content_length":
                len(response.content),

            "metadata":
                metadata,

            "body_file":
                str(output_file),

            "headers_file":
                str(headers_file),
        }
    
