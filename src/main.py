from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from config import (
    BOUNDARY_FILE, INUNDATION_HOURS, INUNDATION_PARAMS, INUNDATION_URL, LATEST_DIR,
    PRECIPITATION_URL, RAINFALL_CUMULATIVE_HOURS, RAINFALL_HOURS_FALLBACK, RAW_DIR,
)
from raster_processor import inundation_geojson, process_inundation, process_rainfall
from spatial import load_districts
from utils import save_json
from wra_client import WRAClient, WRAError

log = logging.getLogger("main")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_inundation(client: WRAClient, districts) -> dict[int, dict[str, Any]]:
    """Fetch forecastHours 0..6 (0=now, 1..6=forecast). Each hour is non-critical."""
    from shapely.geometry import shape

    result: dict[int, dict[str, Any]] = {}
    for hour in INUNDATION_HOURS:
        entry: dict[str, Any] = {"available": False}
        try:
            f = RAW_DIR / f"inundation_h{hour}.bin"
            r = client.get(INUNDATION_URL, f, {**INUNDATION_PARAMS, "forecastHours": hour})
            body = f.read_bytes()
            entry = process_inundation(body, r["metadata"], districts)
            entry["data_time"] = (r["metadata"] or {}).get("TimeStamp")
            if entry.get("available"):
                gj = inundation_geojson(body, r["metadata"], districts)
                save_json(LATEST_DIR / f"inundation_h{hour}.geojson", gj)
                if gj["features"]:
                    b = [shape(x["geometry"]).bounds for x in gj["features"]]
                    entry["extent_wgs84"] = {  # [lon_min, lat_min, lon_max, lat_max]
                        "bbox": [round(min(x[0] for x in b), 5), round(min(x[1] for x in b), 5),
                                 round(max(x[2] for x in b), 5), round(max(x[3] for x in b), 5)],
                        "polygon_count": len(b),
                    }
        except Exception as exc:  # noqa: BLE001
            log.warning("Inundation forecastHours=%s failed (non-critical): %s", hour, exc)
            entry = {"available": False, "reason": str(exc)[:300]}
        log.info("inundation h%s available=%s", hour, entry.get("available"))
        result[hour] = entry
    return result


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
    candidates = [RAINFALL_CUMULATIVE_HOURS] + [
        h for h in RAINFALL_HOURS_FALLBACK if h != RAINFALL_CUMULATIVE_HOURS
    ]
    rf_file = RAW_DIR / "rainfall.bin"
    rf, used_hours, attempts = None, None, []
    for hours in candidates:
        try:
            rf = client.get(PRECIPITATION_URL, rf_file, {"cumulativeHours": hours})
            used_hours = hours
            break
        except WRAError as exc:
            attempts.append({"cumulativeHours": hours, "error": str(exc)[:300]})
            log.warning("cumulativeHours=%s rejected: %s", hours, str(exc)[:200])
            if "HTTP 400" not in str(exc):
                break
    status["rainfall_attempts"] = attempts
    if rf is None:
        status["error"] = "rainfall: all attempts failed"
        save_json(status_file, status)
        return 1  # 不產生新資料 -> 部署被跳過 -> 網站保留上一版

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

    # ---- Inundation 0..6h (non-critical) ----
    inun = fetch_inundation(client, districts)
    save_json(LATEST_DIR / "inundation_statistics.json", {"hours": {str(h): v for h, v in inun.items()}})

    # ---- Public payload (僅公開水文彙整值，不含個資) ----
    rows = []
    for name in districts["name"]:
        r = rain["districts"].get(name, {})
        per_hour: dict[str, Any] = {}
        for h, e in inun.items():
            if e.get("available"):
                d = e.get("districts", {}).get(name, {})
                per_hour[str(h)] = {"area_km2": d.get("area_km2"), "center": d.get("center")}
        now_ = per_hour.get("0", {})
        rows.append({
            "name": name,
            "rainfall_mm": r.get("max_mm"),
            "rainfall_range": r.get("max_range"),
            "rainfall_dry_inferred": r.get("dry_inferred", False),
            "rainfall_coverage_pct": r.get("coverage_pct"),
            "inundation_area_km2": now_.get("area_km2"),       # 相容舊欄位 = 目前即時 (h0)
            "inundation_center": now_.get("center"),
            "inundation": per_hour,                            # {"0": {...}, "1": {...}, ...}
        })

    # 觀察：TimeStamp 約比執行時間早「累積小時數 + 約 2 小時」，推論為統計區間「起點」
    # （1h 與 24h 資料皆符合）；尚未由 WRA 文件證實。
    window_start = (rf["metadata"] or {}).get("TimeStamp")
    window_end = None
    try:
        window_end = (datetime.fromisoformat(window_start) + timedelta(hours=used_hours)).isoformat()
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
        "inundation_hours": {
            str(h): {
                "available": bool(e.get("available")),
                "data_time": e.get("data_time"),
                "message": None if e.get("available") else (e.get("message") or e.get("reason")),
            }
            for h, e in inun.items()
        },
        "inundation_available": bool(inun.get(0, {}).get("available")),
        "districts": rows,
    })

    status["ok"] = True
    save_json(status_file, status)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
