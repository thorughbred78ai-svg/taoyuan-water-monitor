from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any

from config import (
    BOUNDARY_FILE, INUNDATION_URL, LATEST_DIR, PRECIPITATION_URL,
    RAINFALL_CUMULATIVE_HOURS, RAW_DIR,
)
from raster_processor import process_inundation, process_rainfall
from spatial import load_districts
from utils import save_json
from wra_client import WRAClient

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
    try:
        rf_file = RAW_DIR / "rainfall.bin"
        rf = client.get(PRECIPITATION_URL, rf_file,
                        {"cumulativeHours": RAINFALL_CUMULATIVE_HOURS})
        rain = process_rainfall(rf_file.read_bytes(), rf["metadata"], districts)
        save_json(LATEST_DIR / "rainfall_statistics.json", rain)
        status["rainfall"] = {k: rf[k] for k in ("status_code", "content_type", "metadata")}
    except Exception as exc:
        log.exception("Rainfall failed")
        status["error"] = f"rainfall: {exc}"
        save_json(status_file, status)
        return 1  # 不產生新資料 -> 部署被跳過 -> 網站保留上一版

    # ---- Inundation (non-critical) ----
    inun: dict[str, Any] = {"available": False, "reason": "not fetched"}
    try:
        in_file = RAW_DIR / "inundation.bin"
        inr = client.get(INUNDATION_URL, in_file)
        inun = process_inundation(in_file.read_bytes(), inr["metadata"], districts)
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
            "rainfall_mean_mm": r.get("mean_mm"),
            "inundation_area_km2": area,
        })

    save_json(LATEST_DIR / "district_status.json", {
        "updated_at": status["updated_at"],
        "data_time": (rf["metadata"] or {}).get("TimeStamp"),
        "city": "桃園市",
        "cumulative_hours": RAINFALL_CUMULATIVE_HOURS,
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
