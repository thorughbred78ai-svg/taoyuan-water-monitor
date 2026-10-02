from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import rasterio
from rasterio.mask import mask
from shapely.geometry import box


def load_taoyuan_boundary(
    path: Path,
) -> gpd.GeoDataFrame:

    gdf = gpd.read_file(path)

    if gdf.empty:
        raise RuntimeError(
            "Taoyuan boundary is empty."
        )

    if gdf.crs is None:
        raise RuntimeError(
            "Taoyuan boundary CRS is missing."
        )

    return gdf


def select_taoyuan(
    gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:

    # 兼容中文欄位
    county_columns = [
        "COUNTYNAME",
        "county",
        "COUNTY",
        "縣市",
        "縣市名稱",
    ]

    county_column = None

    for column in county_columns:

        if column in gdf.columns:
            county_column = column
            break

    if county_column is None:

        # 如果檔案本身就是桃園行政區
        return gdf

    result = gdf[
        gdf[county_column].astype(str)
        .str.contains("桃園")
    ].copy()

    if result.empty:

        raise RuntimeError(
            "No Taoyuan districts found."
        )

    return result


def clip_raster_to_taoyuan(
    raster_path: Path,
    boundary: gpd.GeoDataFrame,
    output_path: Path,
) -> None:

    with rasterio.open(
        raster_path
    ) as src:

        boundary_proj = boundary.to_crs(
            src.crs
        )

        geometries = [
            geometry
            for geometry in
            boundary_proj.geometry
            if geometry is not None
            and not geometry.is_empty
        ]

        if not geometries:
            raise RuntimeError(
                "No valid boundary geometry."
            )

        clipped, transform = mask(
            src,
            geometries,
            crop=True,
            nodata=src.nodata,
        )

        profile = src.profile.copy()

        profile.update({
            "height": clipped.shape[1],
            "width": clipped.shape[2],
            "transform": transform,
        })

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(clipped)


def raster_intersects_taoyuan(
    raster_path: Path,
    boundary: gpd.GeoDataFrame,
) -> bool:

    with rasterio.open(
        raster_path
    ) as src:

        bounds = src.bounds

        raster_box = box(
            bounds.left,
            bounds.bottom,
            bounds.right,
            bounds.top,
        )

        boundary_proj = boundary.to_crs(
            src.crs
        )

        return boundary_proj.geometry.intersects(
            raster_box
        ).any()
