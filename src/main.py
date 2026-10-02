from future import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
BOUNDARY_FILE,
INUNDATION_URL,
LATEST_DIR,
PRECIPITATION_URL,
RAINFALL_CUMULATIVE_HOURS,
RAW_DIR,
)

from rainfall_processor import (
process_rainfall,
)

from wra_client import WRAClient

def now_iso() -> str:
return datetime.now(
timezone.utc
).isoformat()

def save_json(
path: Path,
data: Any,
) -> None:

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


def validate_boundary() -> dict[str, Any]:

result: dict[str, Any] = {
    "file": str(
        BOUNDARY_FILE
    ),
    "exists": BOUNDARY_FILE.exists(),
}

if not BOUNDARY_FILE.exists():

    result["success"] = False

    result["error"] = (
        "Taoyuan boundary file "
        "does not exist."
    )

    return result

try:

    import geopandas as gpd

    gdf = gpd.read_file(
        BOUNDARY_FILE
    )

    result.update({
        "success": True,
        "crs": (
            str(gdf.crs)
            if gdf.crs
            else None
        ),
        "feature_count": len(gdf),
        "columns": list(
            gdf.columns
        ),
    })

    print()
    print("=" * 70)
    print("Taoyuan Boundary")
    print("=" * 70)

    print(
        "File:",
        BOUNDARY_FILE,
    )

    print(
        "CRS:",
        gdf.crs,
    )

    print(
        "Feature count:",
        len(gdf),
    )

    if len(gdf) != 13:

        print(
            "[WARNING] Expected 13 "
            "Taoyuan districts, got",
            len(gdf),
        )

    if gdf.crs is None:

        print(
            "[WARNING] Boundary CRS "
            "is missing."
        )

except Exception as exc:

    result["success"] = False

    result["error"] = str(exc)

    print(
        "[WARNING] Boundary "
        "validation failed:"
    )

    print(
        repr(exc)
    )

return result


def test_api(
client: WRAClient,
name: str,
url: str,
output_file: Path,
params: dict[str, Any] | None = None,
) -> dict[str, Any]:

print()
print("=" * 70)
print(
    f"WRA API: {name}"
)
print("=" * 70)

print(
    "[WRA] URL:",
    url,
)

print(
    "[WRA] params:",
    json.dumps(
        params,
        ensure_ascii=False,
        indent=2,
    ),
)

print(
    "[WRA] output:",
    output_file,
)

try:

    result = client.get(
        url=url,
        output_file=output_file,
        params=params,
    )

    print()
    print(
        f"[WRA] {name} SUCCESS"
    )

    return {
        "success": True,
        "name": name,
        "url": result.get(
            "url",
            url,
        ),
        "params": params,
        "status_code":
            result.get(
                "status_code"
            ),
        "content_type":
            result.get(
                "content_type"
            ),
        "content_length":
            result.get(
                "content_length"
            ),
        "metadata":
            result.get(
                "metadata"
            ),
        "body_file":
            result.get(
                "body_file"
            ),
        "headers_file":
            result.get(
                "headers_file"
            ),
    }

except Exception as exc:

    print()
    print(
        f"[WRA] {name} FAILED"
    )

    print(
        "[WRA] exception:",
        repr(exc),
    )

    return {
        "success": False,
        "name": name,
        "url": url,
        "params": params,
        "error": str(exc),
    }


def main() -> None:

print("=" * 70)
print("Taoyuan Water Monitor")
print("WRA API Diagnostic")
print("=" * 70)

print(
    "Started:",
    now_iso(),
)

LATEST_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RAW_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

print()
print("=" * 70)
print("[1/4] Loading Taoyuan boundary")
print("=" * 70)

boundary_result = (
    validate_boundary()
)

client = WRAClient()

print()
print("=" * 70)
print("[2/4] Download rainfall")
print("=" * 70)

rainfall_hours = int(
    RAINFALL_CUMULATIVE_HOURS
)

if not 1 <= rainfall_hours <= 24:

    raise ValueError(
        "RAINFALL_CUMULATIVE_HOURS "
        "must be between 1 and 24. "
        f"Current value: "
        f"{rainfall_hours}"
    )

rainfall_params = {
    "cumulativeHours":
        rainfall_hours,
}

print(
    "[RAIN] cumulativeHours:",
    rainfall_hours,
)

print(
    "[RAIN] endpoint:",
    PRECIPITATION_URL,
)

print(
    "[RAIN] params:",
    rainfall_params,
)

rainfall_result = test_api(
    client=client,
    name="precipitation",
    url=PRECIPITATION_URL,
    output_file=(
        RAW_DIR
        / "rainfall.bin"
    ),
    params=rainfall_params,
)

rainfall_processing: dict[
    str, Any
] = {
    "success": False,
    "skipped": True,
    "error": (
        "Rainfall API did not succeed."
    ),
}

if rainfall_result.get(
    "success"
):

    print()
    print("=" * 70)
    print(
        "[2.5/4] Process rainfall raster"
    )
    print("=" * 70)

    rainfall_file = (
        RAW_DIR
        / "rainfall.bin"
    )

    rainfall_metadata_file = (
        RAW_DIR
        / "rainfall.bin.metadata.json"
    )

    rainfall_tif = (
        RAW_DIR
        / "rainfall.tif"
    )

    rainfall_statistics_file = (
        LATEST_DIR
        / "rainfall_statistics.json"
    )

    try:

        rainfall_processing = (
            process_rainfall(
                raster_file=(
                    rainfall_file
                ),
                metadata_file=(
                    rainfall_metadata_file
                ),
                boundary_file=(
                    BOUNDARY_FILE
                ),
                output_tif=(
                    rainfall_tif
                ),
                output_json=(
                    rainfall_statistics_file
                ),
            )
        )

    except Exception as exc:

        rainfall_processing = {
            "success": False,
            "error": str(exc),
            "exception": repr(exc),
        }

        print(
            "[RAIN] Processing failed:"
        )

        print(
            repr(exc)
        )

    print(
        json.dumps(
            rainfall_processing,
            ensure_ascii=False,
            indent=2,
        )
    )

print()
print("=" * 70)
print("[3/4] Download inundation")
print("=" * 70)

inundation_result = test_api(
    client=client,
    name="inundation",
    url=INUNDATION_URL,
    output_file=(
        RAW_DIR
        / "inundation.bin"
    ),
    params=None,
)

status = {
    "updated_at": now_iso(),
    "city": "桃園市",
    "mode": "diagnostic",
    "boundary": boundary_result,
    "rainfall": {
        "endpoint":
            PRECIPITATION_URL,
        "parameters":
            rainfall_params,
        "result":
            rainfall_result,
    },
    "rainfall_processing":
        rainfall_processing,
    "inundation": {
        "endpoint":
            INUNDATION_URL,
        "parameters": None,
        "result":
            inundation_result,
    },
}

status_file = (
    LATEST_DIR
    / "status.json"
)

save_json(
    status_file,
    status,
)

print()
print("=" * 70)
print("[4/4] Diagnostic summary")
print("=" * 70)

print(
    json.dumps(
        status,
        ensure_ascii=False,
        indent=2,
    )
)

print()
print(
    "Status file:",
    status_file,
)

rainfall_ok = (
    rainfall_result.get(
        "success"
    )
    is True
)

inundation_ok = (
    inundation_result.get(
        "success"
    )
    is True
)

processing_ok = (
    rainfall_processing.get(
        "success"
    )
    is True
)

print()
print("=" * 70)
print("Final Result")
print("=" * 70)

print(
    "Boundary:",
    "OK"
    if boundary_result.get(
        "success"
    )
    else "FAILED",
)

print(
    "Rainfall:",
    "OK"
    if rainfall_ok
    else "FAILED",
)

print(
    "Rainfall processing:",
    "OK"
    if processing_ok
    else "FAILED",
)

print(
    "Inundation:",
    "OK"
    if inundation_ok
    else "FAILED",
)

if not rainfall_ok:

    print()
    print(
        "[ERROR] Rainfall API failed."
    )

    print(
        rainfall_result.get(
            "error"
        )
    )

if not processing_ok:

    print()
    print(
        "[ERROR] Rainfall "
        "processing failed."
    )

    print(
        rainfall_processing.get(
            "error"
        )
    )

if not inundation_ok:

    print()
    print(
        "[ERROR] Inundation API failed."
    )

    print(
        inundation_result.get(
            "error"
        )
    )

if (
    not rainfall_ok
    or not inundation_ok
    or not processing_ok
):

    raise RuntimeError(
        "One or more WRA operations "
        "failed. See "
        "data/latest/status.json "
        "and GitHub Actions logs."
    )

print()
print(
    "All WRA APIs and rainfall "
    "processing succeeded."
)


if name == "main":
main()
