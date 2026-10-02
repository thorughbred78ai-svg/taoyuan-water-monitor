
from __future__ import annotations

from pathlib import Path


# =========================================================
# Project
# =========================================================

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)


DATA_DIR = (
    PROJECT_ROOT / "data"
)


LATEST_DIR = (
    DATA_DIR / "latest"
)


RAW_DIR = (
    LATEST_DIR / "raw"
)


BOUNDARY_FILE = (
    DATA_DIR
    / "boundary"
    / "taoyuan_districts.geojson"
)


# =========================================================
# Coordinate Reference Systems
# =========================================================

WGS84 = "EPSG:4326"

TAIWAN_TM2_121 = "EPSG:3826"


# =========================================================
# WRA API
# =========================================================

WRA_BASE_URL = (
    "https://iot.wra.gov.tw"
)


# ---------------------------------------------------------
# Rainfall
# ---------------------------------------------------------
#
# cumulativeHours:
#
# 1 ~ 24 hours
#
# 1 = latest 1-hour cumulative rainfall
# 3 = latest 3-hour cumulative rainfall
# 6 = latest 6-hour cumulative rainfall
# 12 = latest 12-hour cumulative rainfall
# 24 = latest 24-hour cumulative rainfall
#
# ---------------------------------------------------------

RAINFALL_CUMULATIVE_HOURS = 1


PRECIPITATION_URL = (
    f"{WRA_BASE_URL}"
    "/rasterMap/precipitation"
)


# ---------------------------------------------------------
# Inundation
# ---------------------------------------------------------

INUNDATION_URL = (
    f"{WRA_BASE_URL}"
    "/rasterMap/inundation"
)


# =========================================================
# HTTP
# =========================================================

HTTP_TIMEOUT = 120


USER_AGENT = (
    "Taoyuan-Water-Monitor/1.0 "
    "(GitHub Actions)"
)
