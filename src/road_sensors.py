from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import geopandas as gpd
import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import Point
from urllib3.util.retry import Retry

from config import HTTP_RETRIES, HTTP_TIMEOUT, ROAD_SENSOR_URL, USER_AGENT, WGS84, TWD97_TM2

log = logging.getLogger(__name__)
TZ_TW = timezone(timedelta(hours=8))
_TIME_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*(上午|下午)?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?")


def parse_time(text: Any) -> str | None:
    """'2026/10/3 下午 10:00:00' -> ISO8601 (+08:00). 上午12點=0點、下午12點=12點。"""
    m = _TIME_RE.search(str(text or ""))
    if not m:
        return None
    y, mo, d, ampm, h, mi, sec = m.groups()
    hour = int(h)
    if ampm == "下午" and hour < 12:
        hour += 12
    elif ampm == "上午" and hour == 12:
        hour = 0
    try:
        return datetime(int(y), int(mo), int(d), hour, int(mi), int(sec or 0), tzinfo=TZ_TW).isoformat()
    except ValueError:
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_road_sensors() -> list[dict[str, Any]]:
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=HTTP_RETRIES, backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET"}))))
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    log.info("GET road flood sensors")
    resp = session.get(ROAD_SENSOR_URL, timeout=HTTP_TIMEOUT)
    log.info("road sensors HTTP %s size=%d", resp.status_code, len(resp.content))
    resp.raise_for_status()
    return extract_items(resp.json())


def extract_items(data: Any) -> list[dict[str, Any]]:
    """API 一次回傳全部感測點（單一 JSON 陣列）。也容忍常見的包裝格式。"""
    if isinstance(data, dict):
        for key in ("records", "data", "result", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
            if isinstance(data.get(key), dict) and isinstance(data[key].get("records"), list):
                data = data[key]["records"]
                break
    if not isinstance(data, list):
        raise ValueError(f"Unexpected road sensor payload type: {type(data).__name__}")
    seen: set[str] = set()
    out = []
    for it in data:  # 以 id 去重（保留最後一筆）
        if isinstance(it, dict):
            seen.add(str(it.get("id")))
            out.append(it)
    log.info("road sensors: %d items (%d unique ids)", len(out), len(seen))
    return list({str(i.get("id")): i for i in out}.values())


def parse_road_sensors(items: list[dict[str, Any]], districts: gpd.GeoDataFrame,
                       threshold: float) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    for it in items:
        lat, lng = _float(it.get("lat")), _float(it.get("lon"))
        if lat is None or lng is None or not (21 <= lat <= 26 and 119 <= lng <= 123):
            skipped += 1
            continue
        h = _float(it.get("height"))
        rows.append({
            "id": str(it.get("id")), "name": it.get("name"), "address": it.get("address"),
            "lat": round(lat, 6), "lng": round(lng, 6),
            "height": h,
            "data_time": parse_time(it.get("data_time")),
            "district": None,
            "alert": bool(h is not None and h > threshold),
        })

    if rows:  # 以座標判定行政區（來源資料沒有行政區欄位）
        pts = gpd.GeoDataFrame({"i": range(len(rows))},
                               geometry=[Point(r["lng"], r["lat"]) for r in rows], crs=WGS84).to_crs(TWD97_TM2)
        joined = gpd.sjoin(pts, districts[["name", "geometry"]], how="left", predicate="within")
        joined = joined.drop_duplicates("i").sort_values("i")
        for r, name in zip(rows, joined["name"].tolist()):
            r["district"] = name if isinstance(name, str) else None

    times = [r["data_time"] for r in rows if r["data_time"]]
    return {
        "enabled": True,
        "alert_height": threshold,
        "count": len(rows),
        "alert_count": sum(r["alert"] for r in rows),
        "skipped_invalid": skipped,
        "null_height": sum(r["height"] is None for r in rows),
        "latest_data_time": max(times) if times else None,
        "sensors": sorted(rows, key=lambda r: r["id"]),
    }
