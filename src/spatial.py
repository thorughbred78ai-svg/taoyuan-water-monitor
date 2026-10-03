from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
from rasterio import features
from rasterio.transform import Affine

from config import EXPECTED_DISTRICTS, TWD97_TM2


def load_districts(path: Path) -> gpd.GeoDataFrame:
    """Load Taoyuan districts, validate, return GeoDataFrame in EPSG:3826 with `name`."""
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise RuntimeError("Taoyuan boundary is empty.")
    if gdf.crs is None:
        raise RuntimeError("Taoyuan boundary CRS is missing.")
    if "TOWNNAME" not in gdf.columns:
        raise RuntimeError(f"TOWNNAME column missing. columns={list(gdf.columns)}")

    if "COUNTYNAME" in gdf.columns:
        gdf = gdf[gdf["COUNTYNAME"].astype(str).str.contains("桃園")]
    if len(gdf) != EXPECTED_DISTRICTS:
        raise RuntimeError(f"Expected {EXPECTED_DISTRICTS} districts, got {len(gdf)}.")

    gdf = gdf.copy()
    gdf["name"] = gdf["TOWNNAME"].astype(str)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf.to_crs(TWD97_TM2)[["name", "geometry"]]


def district_masks(
    districts: gpd.GeoDataFrame,
    transform: Affine,
    shape: tuple[int, int],
) -> dict[str, np.ndarray]:
    """Boolean mask (True = inside district) for each district on the raster grid."""
    return {
        str(name): features.geometry_mask(
            [geom], out_shape=shape, transform=transform, invert=True
        )
        for name, geom in zip(districts["name"], districts.geometry)
    }
