from __future__ import annotations

import json
import subprocess
from pathlib import Path


def gdalinfo(
    raster_file: Path,
) -> dict:

    print(
        f"[GDAL] Inspecting {raster_file}"
    )

    result = subprocess.run(
        [
            "gdalinfo",
            "-json",
            str(raster_file),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "GDAL cannot read raster.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return json.loads(
        result.stdout
    )


def inspect_raster(
    raster_file: Path,
) -> dict:

    info = gdalinfo(
        raster_file
    )

    print(
        "[GDAL] Driver:",
        info.get("driverShortName"),
    )

    print(
        "[GDAL] Size:",
        info.get("size"),
    )

    print(
        "[GDAL] CRS:",
        info.get("coordinateSystem"),
    )

    print(
        "[GDAL] Bounds:",
        info.get("cornerCoordinates"),
    )

    return info


def convert_to_geotiff(
    source: Path,
    destination: Path,
) -> None:

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "[GDAL] Translating to GeoTIFF:"
    )

    result = subprocess.run(
        [
            "gdal_translate",
            "-of",
            "GTiff",
            str(source),
            str(destination),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "gdal_translate failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
