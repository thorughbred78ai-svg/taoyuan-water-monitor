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

        print("=" * 70)
        print("[WRA] Request")
        print("=" * 70)

        print(f"[WRA] GET {url}")

        try:

            response = self.session.get(
                url,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:

            print(
                "[WRA] REQUEST EXCEPTION:"
            )

            print(
                repr(exc)
            )

            raise RuntimeError(
                f"WRA request failed: {exc}"
            ) from exc


        print(
            "[WRA] status:",
            response.status_code,
        )

        print(
            "[WRA] content-type:",
            response.headers.get(
                "Content-Type"
            ),
        )

        print(
            "[WRA] content-length:",
            response.headers.get(
                "Content-Length"
            ),
        )

        print(
            "[WRA] response-size:",
            len(response.content),
            "bytes",
        )


        # --------------------------------------------------
        # Save HTTP headers regardless of status
        # --------------------------------------------------

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        headers_file = output_file.with_suffix(
            output_file.suffix
            + ".headers.json"
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


        # --------------------------------------------------
        # Handle HTTP error
        # --------------------------------------------------

        if not response.ok:

            print()
            print(
                "[WRA] ERROR RESPONSE:"
            )
            print("-" * 70)

            try:

                error_json = response.json()

                print(
                    json.dumps(
                        error_json,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            except ValueError:

                print(
                    response.text[:10000]
                )

            print("-" * 70)


            # Save error response
            error_file = output_file.with_suffix(
                output_file.suffix
                + ".error.txt"
            )

            error_file.write_text(
                response.text,
                encoding="utf-8",
            )


            # Also save parsed JSON if possible
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
                f"URL: {url}\n"
                f"Response: "
                f"{response.text[:5000]}"
            )


        # --------------------------------------------------
        # Save successful response body
        # --------------------------------------------------

        output_file.write_bytes(
            response.content
        )


        # --------------------------------------------------
        # RasterMepMetaData
        # --------------------------------------------------

        metadata_raw = (
            response.headers.get(
                "RasterMepMetaData"
            )
        )

        metadata_file = output_file.with_suffix(
            output_file.suffix
            + ".metadata.json"
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

                print(
                    "[WRA] RasterMepMetaData "
                    "is not JSON."
                )

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


        # --------------------------------------------------
        # Return information
        # --------------------------------------------------

        return {
            "url": url,

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

