from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LATEST_DIR = DATA_DIR / "latest"
RAW_DIR = LATEST_DIR / "raw"
BOUNDARY_FILE = DATA_DIR / "boundary" / "taoyuan_districts.geojson"

WGS84 = "EPSG:4326"
TWD97_TM2 = "EPSG:3826"

WRA_BASE_URL = "https://iot.wra.gov.tw"
PRECIPITATION_URL = f"{WRA_BASE_URL}/rasterMap/precipitation"
INUNDATION_URL = f"{WRA_BASE_URL}/rasterMap/inundation"

RAINFALL_CUMULATIVE_HOURS = int(os.getenv("RAINFALL_CUMULATIVE_HOURS", "1"))

HTTP_TIMEOUT = (10, 60)  # (connect, read) seconds
HTTP_RETRIES = 3
USER_AGENT = "Taoyuan-Water-Monitor/1.1 (GitHub Actions)"

EXPECTED_DISTRICTS = 13

# 雨量色階對照：{(R, G, B): 代表雨量 mm}
# 必須依 WRA 官方色階填入並人工確認；留空時不會輸出任何雨量數值（寧缺勿錯）。
# 執行後請查看 data/latest/rainfall_statistics.json 的 color_histogram 取得實際出現的顏色。
RAINFALL_LEGEND: dict[tuple[int, int, int], float] = {}
COLOR_TOLERANCE = 12  # RGB 曼哈頓距離容許值
