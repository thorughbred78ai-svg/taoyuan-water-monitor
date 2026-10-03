from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# RainfallElement 子項（不分大小寫）-> 統一 key
KNOWN = {
    "now": "now", "past10min": "past10min", "past1hr": "past1hr", "past3hr": "past3hr",
    "past6hr": "past6hr", "past12hr": "past12hr", "past24hr": "past24hr",
    "past2days": "past2days", "past3days": "past3days",
}


def _num(value: Any) -> tuple[float | None, bool]:
    """Return (value, was_negative_code). Negative values are CWA missing/abnormal codes (assumption)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None, False
    if f < 0:
        return None, True
    return round(f, 1), False


def parse_stations(payload: dict[str, Any], county: str) -> dict[str, Any]:
    records = payload.get("records") or {}
    items = records.get("Station")
    if items is None:
        raise ValueError(
            f"Unexpected CWA format: records keys={list(records.keys())} (expected 'Station')."
        )

    out: list[dict[str, Any]] = []
    unknown_keys: set[str] = set()
    negative_codes = 0

    for st in items:
        geo = st.get("GeoInfo") or {}
        if geo.get("CountyName") != county:
            continue

        coords = geo.get("Coordinates") or []
        pick = next((c for c in coords if c.get("CoordinateName") == "WGS84"), coords[0] if coords else {})
        try:
            lat = float(pick.get("StationLatitude"))
            lng = float(pick.get("StationLongitude"))
        except (TypeError, ValueError):
            log.warning("station %s has no valid coordinates", st.get("StationId"))
            continue

        rain: dict[str, float | None] = {}
        for key, val in (st.get("RainfallElement") or {}).items():
            canon = KNOWN.get(key.lower())
            if canon is None:
                unknown_keys.add(key)
                continue
            raw = val.get("Precipitation") if isinstance(val, dict) else val
            num, neg = _num(raw)
            negative_codes += int(neg)
            rain[canon] = num

        out.append({
            "id": st.get("StationId"),
            "name": st.get("StationName"),
            "district": geo.get("TownName"),
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "altitude_m": geo.get("StationAltitude"),
            "obs_time": (st.get("ObsTime") or {}).get("DateTime"),
            "rain": rain,
        })

    out.sort(key=lambda s: str(s["id"]))
    times = [s["obs_time"] for s in out if s["obs_time"]]
    return {
        "enabled": True,
        "county": county,
        "station_count": len(out),
        "latest_obs_time": max(times) if times else None,
        "negative_code_values": negative_codes,
        "unrecognized_elements": sorted(unknown_keys),
        "stations": out,
    }
