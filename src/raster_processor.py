from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import Affine, from_bounds

from pyproj import Transformer

from config import COLOR_TOLERANCE, DRY_IF_TRANSPARENT, RAINFALL_CLASSES, TWD97_TM2, WGS84
from spatial import district_masks as _district_masks

log = logging.getLogger(__name__)

_MASK_CACHE: dict = {}


def district_masks(districts, transform, shape):
    """Cache masks: 7 inundation hours share one grid, avoid rasterizing 7 times."""
    key = (tuple(transform)[:6], tuple(shape), id(districts))
    if key not in _MASK_CACHE:
        _MASK_CACHE.clear()
        _MASK_CACHE[key] = _district_masks(districts, transform, shape)
    return _MASK_CACHE[key]


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def is_png(data: bytes) -> bool:
    return data.startswith(PNG_SIGNATURE)


def read_rgba(data: bytes) -> np.ndarray:
    """Decode PNG bytes into an (H, W, 4) uint8 array."""
    with MemoryFile(data) as mem, mem.open() as src:
        if src.dtypes[0] != "uint8":
            raise ValueError(f"Unsupported PNG dtype: {src.dtypes[0]}")
        if src.count == 1:
            idx = src.read(1)
            try:
                cmap = src.colormap(1)
            except ValueError:
                cmap = None
            if cmap:
                lut = np.zeros((256, 4), dtype=np.uint8)
                for k, v in cmap.items():
                    lut[k] = v
                return lut[idx]
            return np.stack([idx, idx, idx, np.full_like(idx, 255)], axis=-1)
        bands = src.read()
    if bands.shape[0] == 2:  # gray + alpha
        g, a = bands
        return np.stack([g, g, g, a], axis=-1)
    if bands.shape[0] == 3:
        bands = np.concatenate([bands, np.full_like(bands[:1], 255)])
    return np.moveaxis(bands[:4], 0, -1)


def png_info(data: bytes) -> dict[str, Any]:
    with MemoryFile(data) as mem, mem.open() as src:
        try:
            has_cmap = bool(src.colormap(1)) if src.count == 1 else False
        except ValueError:
            has_cmap = False
        return {
            "bands": src.count,
            "dtype": list(src.dtypes),
            "has_colormap": has_cmap,
            "colorinterp": [str(c) for c in src.colorinterp],
            "nodata": src.nodata,
        }


def build_transform(metadata: dict[str, Any], shape: tuple[int, int]) -> Affine:
    if not metadata or "ULX" not in metadata:
        raise RuntimeError("Raster metadata missing or incomplete.")
    if metadata.get("IsEmptyRasterMap"):
        raise RuntimeError("WRA returned an empty raster map.")
    h, w = shape
    return from_bounds(
        float(metadata["ULX"]), float(metadata["BRY"]),
        float(metadata["BRX"]), float(metadata["ULY"]), w, h,
    )


def decode_rainfall_class(rgba: np.ndarray) -> np.ndarray:
    """Return class index (into RAINFALL_CLASSES) per pixel; -1 = transparent/unmatched."""
    cls = np.full(rgba.shape[:2], -1, dtype=np.int16)
    colors, owner = [], []
    for i, (_, _, rgbs) in enumerate(RAINFALL_CLASSES):
        for c in rgbs:
            colors.append(c)
            owner.append(i)
    if not colors:
        return cls
    colors_a = np.array(colors, dtype=np.int16)
    owner_a = np.array(owner, dtype=np.int16)
    rgb = rgba[..., :3].astype(np.int16)
    dist = np.abs(rgb[:, :, None, :] - colors_a[None, None, :, :]).sum(-1)
    nearest, dmin = dist.argmin(-1), dist.min(-1)
    ok = (rgba[..., 3] > 0) & (dmin <= COLOR_TOLERANCE)
    cls[ok] = owner_a[nearest[ok]]
    return cls


def range_label(lo: float, hi: float | None) -> str:
    if hi is None:
        return f"≥{lo:g}"
    if lo == 0:
        return f"<{hi:g}"
    return f"{lo:g}–{hi:g}"


def color_histogram(rgba: np.ndarray, inside: np.ndarray, top: int = 30) -> list[dict]:
    sel = rgba[inside & (rgba[..., 3] > 0)]
    if sel.size == 0:
        return []
    key = (
        (sel[:, 0].astype(np.int32) << 16)
        | (sel[:, 1].astype(np.int32) << 8)
        | sel[:, 2].astype(np.int32)
    )
    uniq, cnt = np.unique(key, return_counts=True)
    order = np.argsort(cnt)[::-1][:top]
    return [
        {
            "rgb": [int(uniq[i] >> 16), int((uniq[i] >> 8) & 255), int(uniq[i] & 255)],
            "hex": f"#{int(uniq[i]):06x}",
            "pixels": int(cnt[i]),
        }
        for i in order
    ]


def process_rainfall(png: bytes, metadata: dict | None, districts) -> dict[str, Any]:
    if not is_png(png):
        raise ValueError("Rainfall response is not a PNG.")
    rgba = read_rgba(png)
    transform = build_transform(metadata or {}, rgba.shape[:2])
    masks = district_masks(districts, transform, rgba.shape[:2])
    cls = decode_rainfall_class(rgba)
    colored = rgba[..., 3] > 0

    stats: dict[str, Any] = {}
    for name, m in masks.items():
        idx = cls[m & (cls >= 0)]
        n_colored = int((m & colored).sum())
        entry: dict[str, Any] = {
            "max_mm": None, "max_range": None, "dry_inferred": False,
            "valid_pixels": int(idx.size), "colored_pixels": n_colored,
            "coverage_pct": round(100 * n_colored / max(int(m.sum()), 1), 1),
        }
        if idx.size:
            lo, hi, _ = RAINFALL_CLASSES[int(idx.max())]
            entry.update(max_mm=float(lo), max_range=range_label(lo, hi))
        elif n_colored == 0 and DRY_IF_TRANSPARENT:
            entry.update(max_mm=0.0, max_range="<1", dry_inferred=True)
        stats[name] = entry
    any_inside = np.logical_or.reduce(list(masks.values()))
    everywhere = np.ones(rgba.shape[:2], dtype=bool)
    return {
        "legend_configured": bool(RAINFALL_CLASSES),
        "raster": {
            "width": int(rgba.shape[1]),
            "height": int(rgba.shape[0]),
            **png_info(png),
            "colored_pixels_all_taiwan": int(colored.sum()),
            "colored_pixels_taoyuan": int((any_inside & colored).sum()),
            "alpha_values": [int(v) for v in np.unique(rgba[..., 3])[:10]],
        },
        "districts": stats,
        # 桃園範圍內的顏色（無降雨時為空）
        "color_histogram": color_histogram(rgba, any_inside),
        # 全臺有顏色的像素（有降雨時才有內容；用來取得色階）
        "color_histogram_all_taiwan": color_histogram(rgba, everywhere),
    }


_TO_WGS84 = Transformer.from_crs(TWD97_TM2, WGS84, always_xy=True)


def _flood_stats(wet_in_district: np.ndarray, transform: Affine, cell_km2: float) -> dict[str, Any]:
    rows, cols = np.nonzero(wet_in_district)
    out: dict[str, Any] = {
        "area_km2": round(float(rows.size) * cell_km2, 4),
        "wet_pixels": int(rows.size),
    }
    if rows.size:
        x, y = transform * (float(cols.mean()) + 0.5, float(rows.mean()) + 0.5)
        lon, lat = _TO_WGS84.transform(x, y)
        out["center"] = [round(lat, 5), round(lon, 5)]  # [lat, lon]
    return out


def process_inundation(body: bytes, metadata: dict | None, districts) -> dict[str, Any]:
    """PNG -> per-district area of non-transparent pixels (ASSUMPTION: colored = inundated)."""
    if not is_png(body):
        return {
            "available": False,
            "reason": "non-raster response",
            "message": body[:300].decode("utf-8", errors="replace"),
        }
    rgba = read_rgba(body)
    transform = build_transform(metadata or {}, rgba.shape[:2])
    cell_km2 = abs(transform.a * transform.e) / 1e6
    masks = district_masks(districts, transform, rgba.shape[:2])
    wet = rgba[..., 3] > 0
    everywhere = np.ones(rgba.shape[:2], dtype=bool)
    return {
        "available": True,
        "assumption": "non-transparent pixel = inundated (verify against WRA legend)",
        "cell_area_km2": cell_km2,
        "raster": {
            "width": int(rgba.shape[1]),
            "height": int(rgba.shape[0]),
            **png_info(body),
            "colored_pixels_total": int(wet.sum()),
            "alpha_values": [int(v) for v in np.unique(rgba[..., 3])[:10]],
        },
        "color_histogram": color_histogram(rgba, everywhere, top=20),
        "districts": {n: _flood_stats(m & wet, transform, cell_km2) for n, m in masks.items()},
    }


def inundation_geojson(body: bytes, metadata: dict | None, districts,
                       max_features: int = 5000) -> dict[str, Any]:
    """Vectorize inundated pixels (inside Taoyuan districts) into a WGS84 FeatureCollection."""
    import geopandas as gpd
    from rasterio import features as rfeatures
    from shapely.geometry import shape

    empty: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    if not is_png(body):
        return empty
    rgba = read_rgba(body)
    transform = build_transform(metadata or {}, rgba.shape[:2])
    masks = district_masks(districts, transform, rgba.shape[:2])
    inside = np.logical_or.reduce(list(masks.values()))
    wet = (rgba[..., 3] > 0) & inside
    if not wet.any():
        return empty
    geoms = [
        shape(g)
        for g, _ in rfeatures.shapes(wet.astype(np.uint8), mask=wet, transform=transform)
    ][:max_features]
    gdf = gpd.GeoDataFrame(geometry=geoms, crs=TWD97_TM2).to_crs(WGS84)
    return json.loads(gdf.to_json(drop_id=True))
