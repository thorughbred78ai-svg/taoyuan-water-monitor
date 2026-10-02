from future import annotations

from pathlib import Path

PROJECT_ROOT = (
Path(file).resolve().parent.parent
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

WGS84 = "EPSG:4326"

TAIWAN_TM2_121 = "EPSG:3826"

WRA_BASE_URL = (
"https://iot.wra.gov.tw"
)

RAINFALL_CUMULATIVE_HOURS = 1

PRECIPITATION_URL = (
f"{WRA_BASE_URL}"
"/rasterMap/precipitation"
)

INUNDATION_URL = (
f"{WRA_BASE_URL}"
"/rasterMap/inundation"
)

HTTP_TIMEOUT = 120

USER_AGENT = (
"Taoyuan-Water-Monitor/1.0 "
"(GitHub Actions)"
)
