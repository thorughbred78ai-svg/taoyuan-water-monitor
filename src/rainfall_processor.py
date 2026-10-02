from future import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.transform import from_bounds

TAIWAN_TM2_121 = "EPSG:3826"

def load_metadata(metadata_file: Path) -> dict[str, Any]:
"""Load WRA RasterMapMetaData."""

if not metadata_file.exists():
    raise FileNotFoundError(
        f"Raster metadata file not found: {metadata_file}"
    )

data = json.loads(
    metadata_file.read_text(
        encoding="utf-8"
    )
)

required = [
    "ULX",
    "ULY",
    "BRX",
    "BRY",
    "Width",
    "Height",
    "IsEmptyRasterMap",
]

missing = [
    key
    for key in required
    if key not in data
]

if missing:
    raise ValueError(
        "Missing WRA raster metadata fields: "
        + ", ".join(missing)
    )

return data


def inspect_png(raster_file: Path) -> dict[str, Any]:
"""
Inspect the downloaded WRA PNG.

Do not assume RGB/color values are rainfall
millimetres.
"""

if not raster_file.exists():
    raise FileNotFoundError(
        f"Raster file not found: {raster_file}"
    )

data = raster_file.read_bytes()

png_signature = b"\x89PNG\r\n\x1a\n"

if not data.startswith(png_signature):
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
            "dtype": list(src.dtypes),
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
            "bounds": [
                float(value)
                for value in src.bounds
            ],
        }


def build_georeferenced_raster(
raster_file: Path,
metadata_file: Path,
output_tif: Path,
) -> dict[str, Any]:
"""
Convert WRA PNG into a georeferenced GeoTIFF.

WRA metadata supplies the projected bounding box.
"""

metadata = load_metadata(
    metadata_file
)

if metadata["IsEmptyRasterMap"]:
    raise RuntimeError(
        "WRA returned an empty rainfall raster."
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
            width=src.width,
            height=src.height,
            compress="deflate",
        )

        with rasterio.open(
            output_tif,
            "w",
            **profile,
        ) as dst:

            for band_number in range(
                1,
                src.count + 1,
            ):
                dst.write(
                    src.read(band_number),
                    band_number,
                )

return {
    "file": str(output_tif),
    "crs": TAIWAN_TM2_121,
    "width": int(metadata["Width"]),
    "height": int(metadata["Height"]),
    "bounds": {
        "left": float(metadata["ULX"]),
        "bottom": float(metadata["BRY"]),
        "right": float(metadata["BRX"]),
        "top": float(metadata["ULY"]),
    },
}


def numeric_statistics(
values: np.ndarray,
) -> dict[str, Any]:
"""Calculate basic statistics."""

values = values[
    np.isfinite(values)
]

if values.size == 0:
    return {
        "valid_pixels": 0,
        "min": None,
        "max": None,
        "mean": None,
        "median": None,
        "sum": None,
    }

return {
    "valid_pixels": int(values.size),
    "min": float(np.min(values)),
    "max": float(np.max(values)),
    "mean": float(np.mean(values)),
    "median": float(np.median(values)),
    "sum": float(np.sum(values)),
}


def calculate_district_statistics(
raster_file: Path,
boundary_file: Path,
) -> list[dict[str, Any]]:
"""
Calculate zonal statistics for Taoyuan districts.

Only a single-band numeric raster is accepted.

RGB/RGBA/colorized rainfall maps are intentionally
rejected because their pixel colors cannot safely
be interpreted as millimetres without a WRA legend.
"""

gdf = gpd.read_file(
    boundary_file
)

if gdf.empty:
    raise RuntimeError(
        "Taoyuan boundary is empty."
    )

if gdf.crs is None:
    raise RuntimeError(
        "Taoyuan boundary has no CRS."
    )

with rasterio.open(
    raster_file
) as src:

    if src.count != 1:
        raise RuntimeError(
            "Rainfall PNG contains "
            f"{src.count} bands. "
            "Direct rainfall statistics are disabled "
            "until the WRA color/value mapping is known."
        )

    if src.crs is None:
        raise RuntimeError(
            "Rainfall raster has no CRS."
        )

    if gdf.crs != src.crs:
        gdf = gdf.to_crs(
            src.crs
        )

    results: list[dict[str, Any]] = []

    for _, district in gdf.iterrows():

        geometry = [
            district.geometry
        ]

        clipped, _ = mask(
            src,
            geometry,
            crop=True,
            filled=False,
        )

        values = clipped[0].compressed()

        statistics = numeric_statistics(
            values
        )

        result = {
            "town_id": str(
                district.get(
                    "TOWNID",
                    "",
                )
            ),
            "town_code": str(
                district.get(
                    "TOWNCODE",
                    "",
                )
            ),
            "town_name": str(
                district.get(
                    "TOWNNAME",
                    "",
                )
            ),
            "town_eng": str(
                district.get(
                    "TOWNENG",
                    "",
                )
            ),
        }

        result.update(
            statistics
        )

        results.append(
            result
        )

    return results


def save_json(
path: Path,
data: Any,
) -> None:
"""Save UTF-8 JSON."""

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
"""
Process the WRA rainfall raster.

Steps:

1. Inspect PNG.
2. Apply WRA geospatial metadata.
3. Write GeoTIFF.
4. Attempt district statistics.
5. Save processing result as JSON.
"""

inspection = inspect_png(
    raster_file
)

georeferenced = build_georeferenced_raster(
    raster_file=raster_file,
    metadata_file=metadata_file,
    output_tif=output_tif,
)

result: dict[str, Any] = {
    "raster": inspection,
    "georeferenced": georeferenced,
}

try:

    districts = calculate_district_statistics(
        raster_file=output_tif,
        boundary_file=boundary_file,
    )

    result["statistics_available"] = True
    result["districts"] = districts

except RuntimeError as exc:

    result["statistics_available"] = False
    result["statistics_error"] = str(
        exc
    )

save_json(
    output_json,
    result,
)

return result
