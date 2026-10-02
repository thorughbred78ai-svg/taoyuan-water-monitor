from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import (
    BOUNDARY_FILE,
    INUNDATION_URL,
    LATEST_DIR,
    PRECIPITATION_URL,
    RAW_DIR,
)

from raster import (
    inspect_raster,
)

from spatial import (
    load_taoyuan_boundary,
    select_taoyuan,
)

from wra_client import WRAClient


def now_iso() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def save_json(
    path: Path,
    data: dict,
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


def main():

    print("=" * 70)
    print("Taoyuan Water Monitor")
    print("=" * 70)

    LATEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------
    # Boundary
    # --------------------------------------------------

    print(
        "[1/5] Loading Taoyuan boundary..."
    )

    boundary = load_taoyuan_boundary(
        BOUNDARY_FILE
    )

    boundary = select_taoyuan(
        boundary
    )

    print(
        "District count:",
        len(boundary),
    )

    print(
        "CRS:",
        boundary.crs,
    )

    # --------------------------------------------------
    # WRA client
    # --------------------------------------------------

    client = WRAClient()

    # --------------------------------------------------
    # Rainfall
    # --------------------------------------------------

    print(
        "[2/5] Download rainfall..."
    )

    rainfall_raw = (
        RAW_DIR
        / "rainfall.bin"
    )

    rainfall_result = client.get(
        PRECIPITATION_URL,
        rainfall_raw,
    )

    # --------------------------------------------------
    # Inundation
    # --------------------------------------------------

    print(
        "[3/5] Download inundation..."
    )

    inundation_raw = (
        RAW_DIR
        / "inundation.bin"
    )

    inundation_result = client.get(
        INUNDATION_URL,
        inundation_raw,
    )

    # --------------------------------------------------
    # Inspect Raster
    # --------------------------------------------------

    print(
        "[4/5] Inspecting Raster..."
    )

    rainfall_info = None
    inundation_info = None

    try:

        rainfall_info = inspect_raster(
            rainfall_raw
        )

    except Exception as exc:

        print(
            "[WARN] Rainfall is not directly "
            f"GDAL-readable: {exc}"
        )

    try:

        inundation_info = inspect_raster(
            inundation_raw
        )

    except Exception as exc:

        print(
            "[WARN] Inundation is not directly "
            f"GDAL-readable: {exc}"
        )

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    print(
        "[5/5] Writing status..."
    )

    status = {
        "updated_at": now_iso(),
        "city": "桃園市",

        "rainfall": {
            "url": PRECIPITATION_URL,
            "downloaded": (
                rainfall_raw.exists()
            ),
            "content_type":
                rainfall_result.get(
                    "content_type"
                ),
            "size_bytes":
                rainfall_result.get(
                    "content_length"
                ),
            "gdal_readable":
                rainfall_info is not None,
        },

        "inundation": {
            "url": INUNDATION_URL,
            "downloaded": (
                inundation_raw.exists()
            ),
            "content_type":
                inundation_result.get(
                    "content_type"
                ),
            "size_bytes":
                inundation_result.get(
                    "content_length"
                ),
            "gdal_readable":
                inundation_info is not None,
        },
    }

    save_json(
        LATEST_DIR / "status.json",
        status,
    )

    # --------------------------------------------------
    # District status
    #
    # 第一版先建立行政區清單。
    # Raster 數值語意確認後，再加入
    # rainfall_mm / inundation_area_km2。
    # --------------------------------------------------

    district_name_column = None

    for column in [
        "TOWNNAME",
        "townname",
        "TOWN",
        "鄉鎮市區",
        "鄉鎮市區名稱",
        "district",
    ]:

        if column in boundary.columns:
            district_name_column = column
            break

    districts = []

    for _, row in boundary.iterrows():

        name = (
            str(row[district_name_column])
            if district_name_column
            else "Unknown"
        )

        districts.append({
            "name": name,
            "rainfall_mm": None,
            "inundation_area_km2": None,
        })

    district_status = {
        "updated_at": now_iso(),
        "city": "桃園市",
        "districts": districts,
    }

    save_json(
        LATEST_DIR
        / "district_status.json",
        district_status,
    )

    print(
        "ETL completed."
    )


if __name__ == "__main__":
    main()

