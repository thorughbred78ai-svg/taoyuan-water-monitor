from pathlib import Path


# =========================================================
# WRA API
# =========================================================

WRA_BASE_URL = (
    "https://iot.wra.gov.tw"
)


PRECIPITATION_URL = (
    f"{WRA_BASE_URL}"
    "/rasterMap/precipitation"
)


INUNDATION_URL = (
    f"{WRA_BASE_URL}"
    "/rasterMap/inundation"
)


PRECIPITATION_METADATA_URL = (
    f"{WRA_BASE_URL}"
    "/rasterMap/precipitation/"
    "rasterMapMetaData"
)


INUNDATION_METADATA_URL = (
    f"{WRA_BASE_URL}"
    "/rasterMap/inundation/"
    "rasetMapMetaData"
)


# =========================================================
# Project paths
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
# CRS
# =========================================================

WGS84 = "EPSG:4326"

TAIWAN_TM2_121 = "EPSG:3826"


# =========================================================
# HTTP
# =========================================================

HTTP_TIMEOUT = 120


USER_AGENT = (
    "Taoyuan-Water-Monitor/1.0 "
    "(GitHub Actions)"
)
