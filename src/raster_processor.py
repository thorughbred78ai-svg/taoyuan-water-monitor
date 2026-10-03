from __future__ import annotations

import logging
from typing import Any

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import Affine, from_bounds

from config import COLOR_TOLERANCE, RAINFALL_LEGEND
from spatial import district_masks

log = logging.getLogger(__name__)

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


def decode_rainfall_mm(rgba: np.ndarray) -> np.ndarray:
    """Map legend colors to mm. NaN where transparent / unmatched / no legend."""
    mm = np.full(rgba.shape[:2], np.nan, dtype=np.float32)
    if not RAINFALL_LEGEND:
        return mm
    colors = np.array(list(RAINFALL_LEGEND.keys()), dtype=np.int16)
    values = np.array(list(RAINFALL_LEGEND.values()), dtype=np.float32)
    rgb = rgba[..., :3].astype(np.int16)
    dist = np.abs(rgb[:, :, None, :] - colors[None, None, :, :]).sum(-1)
    nearest, dmin = dist.argmin(-1), dist.min(-1)
    ok = (rgba[..., 3] > 0) & (dmin <= COLOR_TOLERANCE)
    mm[ok] = values[nearest[ok]]
    return mm


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
    mm = decode_rainfall_mm(rgba)
    colored = rgba[..., 3] > 0

    stats: dict[str, Any] = {}
    for name, m in masks.items():
        vals = mm[m & ~np.isnan(mm)]
        stats[name] = {
            "max_mm": round(float(vals.max()), 1) if vals.size else None,
            "mean_mm": round(float(vals.mean()), 1) if vals.size else None,
            "valid_pixels": int(vals.size),
            "colored_pixels": int((m & colored).sum()),
        }
    any_inside = np.logical_or.reduce(list(masks.values()))
    return {
        "legend_configured": bool(RAINFALL_LEGEND),
        "raster": {"width": int(rgba.shape[1]), "height": int(rgba.shape[0])},
        "districts": stats,
        "color_histogram": color_histogram(rgba, any_inside),
    }


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
    return {
        "available": True,
        "assumption": "non-transparent pixel = inundated (verify against WRA legend)",
        "cell_area_km2": cell_km2,
        "districts": {
            n: {"area_km2": round(float((m & wet).sum()) * cell_km2, 3)}
            for n, m in masks.items()
        },
    }
