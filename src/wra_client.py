
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
    ) -> dict[str, Any]:

        print(f"[WRA] GET {url}")

        response = self.session.get(
            url,
            timeout=self.timeout,
        )

        print(
            "[WRA] status:",
            response.status_code,
        )

        print(
            "[WRA] content-type:",
            response.headers.get("Content-Type"),
        )

        response.raise_for_status()

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_file.write_bytes(
            response.content
        )

        # ----------------------------------------------
        # Save all HTTP headers
        # ----------------------------------------------

        headers = {
            key: value
            for key, value in response.headers.items()
        }

        headers_file = output_file.with_suffix(
            output_file.suffix + ".headers.json"
        )

        headers_file.write_text(
            json.dumps(
                headers,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # ----------------------------------------------
        # RasterMepMetaData
        # ----------------------------------------------

        metadata_raw = response.headers.get(
            "RasterMepMetaData"
        )

        metadata_file = output_file.with_suffix(
            output_file.suffix + ".metadata.json"
        )

        metadata = None

        if metadata_raw:

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
                "[WRA] RasterMepMetaData header "
                "not found."
            )

        return {
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get(
                "Content-Type"
            ),
            "content_length": len(
                response.content
            ),
            "metadata": metadata,
            "body_file": str(output_file),
        }
