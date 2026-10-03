
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from config import (
    BOUNDARY_FILE, INUNDATION_PARAMS, INUNDATION_URL, LATEST_DIR, PRECIPITATION_URL,
    RAINFALL_CUMULATIVE_HOURS, RAINFALL_HOURS_FALLBACK, RAW_DIR,
)
from raster_processor import inundation_geojson, process_inundation, process_rainfall
from spatial import load_districts
from utils import save_json
from wra_client import WRAClient, WRAError

log = logging.getLogger("main")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    status: dict[str, Any] = {"updated_at": now_iso(), "city": "桃園市", "ok": False}
    status_file = LATEST_DIR / "status.json"

    if not 1 <= RAINFALL_CUMULATIVE_HOURS <= 24:
        log.error("RAINFALL_CUMULATIVE_HOURS must be 1..24")
        return 1

    try:
        districts = load_districts(BOUNDARY_FILE)
    except Exception as exc:
        log.exception("Boundary validation failed")
        status["error"] = f"boundary: {exc}"
        save_json(status_file, status)
        return 1

    client = WRAClient()

    # ---- Rainfall (critical) ----
    # 先用設定值；若 API 以 HTTP 400 拒絕參數，依序探測其他小時數並記錄實際使用值
    candidates = [RAINFALL_CUMULATIVE_HOURS] + [
        h for h in RAINFALL_HOURS_FALLBACK if h != RAINFALL_CUMULATIVE_HOURS
    ]
    rf_file = RAW_DIR / "rainfall.bin"
    rf = None
    used_hours = None
    attempts: list[dict[str, Any]] = []
    for hours in candidates:
        try:
            rf = client.get(PRECIPITATION_URL, rf_file, {"cumulativeHours": hours})
            used_hours = hours
            break
        except WRAError as exc:
            attempts.append({"cumulativeHours": hours, "error": str(exc)[:300]})
            log.warning("cumulativeHours=%s rejected: %s", hours, str(exc)[:200])
            if "HTTP 400" not in str(exc):  # 非參數錯誤（5xx/網路）不必探測
                break
    status["rainfall_attempts"] = attempts
    if rf is None:
        status["error"] = "rainfall: all attempts failed"
        save_json(status_file, status)
        return 1  # 不產生新資料 -> 部署被跳過 -> 網站保留上一版
    if used_hours != RAINFALL_CUMULATIVE_HOURS:
        log.warning("Using cumulativeHours=%s instead of %s", used_hours, RAINFALL_CUMULATIVE_HOURS)

    try:
        rain = process_rainfall(rf_file.read_bytes(), rf["metadata"], districts)
        save_json(LATEST_DIR / "rainfall_statistics.json", rain)
        status["rainfall"] = {
            "cumulative_hours": used_hours,
            **{k: rf[k] for k in ("status_code", "content_type", "metadata")},
        }
    except Exception as exc:
        log.exception("Rainfall processing failed")
        status["error"] = f"rainfall processing: {exc}"
        save_json(status_file, status)
        return 1

    # ---- Inundation (non-critical) ----
    inun: dict[str, Any] = {"available": False, "reason": "not fetched"}
    try:
        in_file = RAW_DIR / "inundation.bin"
        inr = client.get(INUNDATION_URL, in_file, INUNDATION_PARAMS or None)
        inun = process_inundation(in_file.read_bytes(), inr["metadata"], districts)
        if inun.get("available"):
            flood_gj = inundation_geojson(in_file.read_bytes(), inr["metadata"], districts)
            save_json(LATEST_DIR / "inundation.geojson", flood_gj)
            if flood_gj["features"]:
                from shapely.geometry import shape
                bounds = [shape(f["geometry"]).bounds for f in flood_gj["features"]]
                inun["extent_wgs84"] = {  # [lon_min, lat_min, lon_max, lat_max]，便於與現場/感測器核對
                    "bbox": [
                        round(min(b[0] for b in bounds), 5), round(min(b[1] for b in bounds), 5),
                        round(max(b[2] for b in bounds), 5), round(max(b[3] for b in bounds), 5),
                    ],
                    "polygon_count": len(bounds),
                }
        status["inundation"] = {k: inr[k] for k in ("status_code", "content_type", "content_length")}
    except Exception as exc:
        log.warning("Inundation failed (non-critical): %s", exc)
        inun = {"available": False, "reason": str(exc)}
        status["inundation_error"] = str(exc)
    save_json(LATEST_DIR / "inundation_statistics.json", inun)

    # ---- Public payload (僅公開水文彙整值，不含個資) ----
    rows = []
    for name in districts["name"]:
        r = rain["districts"].get(name, {})
        area = None
        if inun.get("available"):
            area = inun.get("districts", {}).get(name, {}).get("area_km2")
        rows.append({
            "name": name,
            "rainfall_mm": r.get("max_mm"),
            "rainfall_range": r.get("max_range"),
            "rainfall_dry_inferred": r.get("dry_inferred", False),
            "rainfall_coverage_pct": r.get("coverage_pct"),
            "inundation_area_km2": area,
        })

    # 觀察：TimeStamp 約比執行時間早「累積小時數 + 約 2 小時」，推論為統計區間「起點」
    # （1h 與 24h 兩組資料皆符合）；尚未由 WRA 文件證實。
    window_start = (rf["metadata"] or {}).get("TimeStamp")
    window_end = None
    try:
        window_end = (
            datetime.fromisoformat(window_start) + timedelta(hours=used_hours)
        ).isoformat()
    except (TypeError, ValueError):
        pass

    save_json(LATEST_DIR / "district_status.json", {
        "updated_at": status["updated_at"],
        "window_start": window_start,
        "window_end": window_end,
        "data_time": window_end or window_start,
        "city": "桃園市",
        "cumulative_hours": used_hours,
        "rainfall_legend_configured": rain["legend_configured"],
        "inundation_available": bool(inun.get("available")),
        "districts": rows,
    })

    status["ok"] = True
    save_json(status_file, status)
    if not rain["legend_configured"]:
        log.warning("RAINFALL_LEGEND is empty: rainfall values are null. "
                    "See rainfall_statistics.json color_histogram.")
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
