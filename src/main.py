from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from concurrent.futures import ThreadPoolExecutor

from config import (
    BOUNDARY_FILE, INUNDATION_HOURS, INUNDATION_PARAMS, INUNDATION_URL, LATEST_DIR,
    PRECIPITATION_URL, RAINFALL_ALERT_HOURS, RAINFALL_ALERT_MM, RAINFALL_HOURS,
    RAINFALL_WORKERS, RAW_DIR,
)
from raster_processor import (
    inundation_geojson, process_inundation, process_rainfall, rainfall_cells_geojson,
)
from spatial import load_districts
from utils import save_json
from wra_client import WRAClient

log = logging.getLogger("main")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_rainfall(client: WRAClient, districts) -> dict[int, dict[str, Any]]:
    """Download cumulativeHours 1..24 concurrently, then process sequentially."""
    def download(h: int) -> tuple[int, dict[str, Any]]:
        try:
            r = client.get(PRECIPITATION_URL, RAW_DIR / f"rainfall_h{h:02d}.bin",
                           {"cumulativeHours": h})
            return h, {"download": r}
        except Exception as exc:  # noqa: BLE001
            return h, {"reason": str(exc)[:300]}

    with ThreadPoolExecutor(max_workers=RAINFALL_WORKERS) as ex:
        downloaded = dict(ex.map(download, RAINFALL_HOURS))

    result: dict[int, dict[str, Any]] = {}
    for h in RAINFALL_HOURS:  # masks cache 非 thread-safe，故處理階段循序執行
        d = downloaded[h]
        if "download" not in d:
            log.warning("rainfall h%s download failed: %s", h, d["reason"])
            result[h] = {"ok": False, "reason": d["reason"]}
            continue
        try:
            body = (RAW_DIR / f"rainfall_h{h:02d}.bin").read_bytes()
            meta = d["download"]["metadata"]
            stats = process_rainfall(
                body, meta, districts, diagnostics=(h == 1),
                alert_mm=RAINFALL_ALERT_MM if h == RAINFALL_ALERT_HOURS else None,
            )
            save_json(LATEST_DIR / f"rainfall_h{h}.geojson",
                      rainfall_cells_geojson(body, meta, districts))
            result[h] = {"ok": True, "stats": stats, "timestamp": (meta or {}).get("TimeStamp")}
        except Exception as exc:  # noqa: BLE001
            log.warning("rainfall h%s processing failed: %s", h, exc)
            result[h] = {"ok": False, "reason": str(exc)[:300]}
    log.info("rainfall ok hours: %s", [h for h, e in result.items() if e["ok"]])
    return result


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

    try:
        districts = load_districts(BOUNDARY_FILE)
    except Exception as exc:
        log.exception("Boundary validation failed")
        status["error"] = f"boundary: {exc}"
        save_json(status_file, status)
        return 1

    client = WRAClient()

    # ---- Rainfall 1..24h (至少一個延時成功才算成功) ----
    rain = fetch_rainfall(client, districts)
    ok_hours = sorted(h for h, e in rain.items() if e.get("ok"))
    status["rainfall"] = {
        "available_hours": ok_hours,
        "failed": {str(h): e.get("reason") for h, e in rain.items() if not e.get("ok")},
    }
    if not ok_hours:
        status["error"] = "rainfall: all cumulativeHours failed"
        save_json(status_file, status)
        return 1  # 不產生新資料 -> 部署被跳過 -> 網站保留上一版
    default_hour = ok_hours[0]
    save_json(LATEST_DIR / "rainfall_statistics.json", {
        "hours": {
            str(h): (rain[h]["stats"] if h == default_hour else
                     {"max_range": {n: v["max_range"] for n, v in rain[h]["stats"]["districts"].items()}})
            for h in ok_hours
        }
    })

    # ---- Inundation 0..6h (non-critical) ----
    inun = fetch_inundation(client, districts)
    save_json(LATEST_DIR / "inundation_statistics.json", {"hours": {str(h): v for h, v in inun.items()}})

    # ---- Public payload (僅公開水文彙整值，不含個資) ----
    # 觀察：TimeStamp 約比執行時間早「累積小時數 + 約 2 小時」，推論為統計區間「起點」
    # （1h 與 24h 資料皆符合）；尚未由 WRA 文件證實。
    rain_hours_info: dict[str, Any] = {}
    for h in RAINFALL_HOURS:
        e = rain[h]
        info: dict[str, Any] = {"available": bool(e.get("ok"))}
        if e.get("ok"):
            ts = e.get("timestamp")
            info["window_start"] = ts
            try:
                info["window_end"] = (datetime.fromisoformat(ts) + timedelta(hours=h)).isoformat()
            except (TypeError, ValueError):
                info["window_end"] = None
        else:
            info["message"] = e.get("reason")
        rain_hours_info[str(h)] = info

    rows = []
    for name in districts["name"]:
        rf_by_hour: dict[str, Any] = {}
        for h in ok_hours:
            r = rain[h]["stats"]["districts"].get(name, {})
            rf_by_hour[str(h)] = {
                "mm": r.get("max_mm"), "range": r.get("max_range"),
                "dry": r.get("dry_inferred", False), "coverage": r.get("coverage_pct"),
                "alert": r.get("alert"),
            }
        per_hour: dict[str, Any] = {}
        for h, e in inun.items():
            if e.get("available"):
                d = e.get("districts", {}).get(name, {})
                per_hour[str(h)] = {"area_km2": d.get("area_km2"), "center": d.get("center")}
        now_ = per_hour.get("0", {})
        dflt = rf_by_hour.get(str(default_hour), {})
        rows.append({
            "name": name,
            "rainfall": rf_by_hour,                           # {"1": {...}, ..., "24": {...}}
            "rainfall_mm": dflt.get("mm"),                    # 相容舊欄位 = 預設延時
            "rainfall_range": dflt.get("range"),
            "rainfall_dry_inferred": dflt.get("dry", False),
            "inundation_area_km2": now_.get("area_km2"),      # 相容舊欄位 = 目前即時 (h0)
            "inundation_center": now_.get("center"),
            "inundation": per_hour,                           # {"0": {...}, ..., "6": {...}}
        })

    save_json(LATEST_DIR / "district_status.json", {
        "updated_at": status["updated_at"],
        "city": "桃園市",
        "default_rainfall_hours": default_hour,
        "rainfall_alert": {"hours": RAINFALL_ALERT_HOURS, "mm": RAINFALL_ALERT_MM},
        "rainfall_cell_size_m": rain[default_hour]["stats"].get("cell_size_m"),
        "rainfall_hours": rain_hours_info,
        "rainfall_legend_configured": rain[default_hour]["stats"]["legend_configured"],
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
