from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds


TAIWAN_TM2_121 = "EPSG:3826"


def load_metadata(
    metadata_file: Path,
) -> dict[str, Any]:
    if not metadata_file.exists():
        raise FileNotFoundError(
            f"Raster metadata file not found: "
            f"{metadata_file}"
        )

    return json.loads(
        metadata_file.read_text(
            encoding="utf-8"
        )
    )


def inspect_png(
    raster_file: Path,
) -> dict[str, Any]:
    if not raster_file.exists():
        raise FileNotFoundError(
            f"Raster file not found: "
            f"{raster_file}"
        )

    data = raster_file.read_bytes()

    png_signature = (
        b"\x89PNG\r\n\x1a\n"
    )

    if not data.startswith(
        png_signature
    ):
        raise ValueError(
            "WRA rainfall file is not a PNG."
        )

    with MemoryFile(data) as memfile:
        with memfile.open() as src:
            return {
                "driver": src.driver,
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "dtype": list(
                    src.dtypes
                ),
                "colorinterp": [
                    str(value)
                    for value in src.colorinterp
                ],
                "nodata": src.nodata,
                "crs": (
                    str(src.crs)
                    if src.crs
                    else None
                ),
            }


def build_georeferenced_raster(
    raster_file: Path,
    metadata_file: Path,
    output_tif: Path,
) -> dict[str, Any]:
    metadata = load_metadata(
        metadata_file
    )

    if metadata.get(
        "IsEmptyRasterMap"
    ):
        raise RuntimeError(
            "WRA returned an empty "
            "rainfall raster."
        )

    png_data = raster_file.read_bytes()

    with MemoryFile(png_data) as memfile:
        with memfile.open() as src:
            transform = from_bounds(
                float(metadata["ULX"]),
                float(metadata["BRY"]),
                float(metadata["BRX"]),
                float(metadata["ULY"]),
                src.width,
                src.height,
            )

            output_tif.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            profile = src.profile.copy()

            profile.update(
                driver="GTiff",
                crs=TAIWAN_TM2_121,
                transform=transform,
                compress="deflate",
            )

            with rasterio.open(
                output_tif,
                "w",
                **profile,
            ) as dst:
                for band in range(
                    1,
                    src.count + 1,
                ):
                    dst.write(
                        src.read(band),
                        band,
                    )

            width = src.width
            height = src.height
            count = src.count

    return {
        "file": str(output_tif),
        "crs": TAIWAN_TM2_121,
        "width": width,
        "height": height,
        "count": count,
    }


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


def process_rainfall(
    raster_file: Path,
    metadata_file: Path,
    boundary_file: Path,
    output_tif: Path,
    output_json: Path,
) -> dict[str, Any]:
    del boundary_file

    print()
    print("=" * 70)
    print("Rainfall raster inspection")
    print("=" * 70)

    print(
        "[RAIN] raster:",
        raster_file,
    )

    print(
        "[RAIN] metadata:",
        metadata_file,
    )

    print(
        "[RAIN] output:",
        output_tif,
    )

    inspection = inspect_png(
        raster_file
    )

    print(
        "[RAIN] PNG driver:",
        inspection["driver"],
    )

    print(
        "[RAIN] width:",
        inspection["width"],
    )

    print(
        "[RAIN] height:",
        inspection["height"],
    )

    print(
        "[RAIN] bands:",
        inspection["count"],
    )

    print(
        "[RAIN] dtype:",
        inspection["dtype"],
    )

    georeferenced = (
        build_georeferenced_raster(
            raster_file=raster_file,
            metadata_file=metadata_file,
            output_tif=output_tif,
        )
    )

    result = {
        "success": True,
        "raster": inspection,
        "georeferenced": georeferenced,
        "statistics_available": False,
        "statistics_error": (
            "District statistics are "
            "not enabled yet."
        ),
    }

    save_json(
        output_json,
        result,
    )

    print(
        "[RAIN] GeoTIFF created:",
        output_tif,
    )

    print(
        "[RAIN] Processing result:",
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    return result
