from pathlib import Path
import json
import requests


class WRAClient:

    def __init__(self, timeout=120):
        self.timeout = timeout

    def get_raster(self, url, output_file):
        response = requests.get(
            url,
            timeout=self.timeout
        )

        response.raise_for_status()

        metadata = response.headers.get(
            "RasterMepMetaData"
        )

        output_file = Path(output_file)
        output_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        output_file.write_bytes(
            response.content
        )

        metadata_file = output_file.with_suffix(
            ".metadata.json"
        )

        if metadata:
            try:
                metadata_json = json.loads(metadata)

                metadata_file.write_text(
                    json.dumps(
                        metadata_json,
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding="utf-8"
                )

            except json.JSONDecodeError:
                metadata_file.write_text(
                    metadata,
                    encoding="utf-8"
                )

        return {
            "status_code": response.status_code,
            "content_type": response.headers.get(
                "Content-Type"
            ),
            "metadata": metadata,
            "file": str(output_file),
        }
