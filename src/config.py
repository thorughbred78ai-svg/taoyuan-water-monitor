from __future__ import annotations

import json
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

# HTTP 400 拒絕設定值時，依序嘗試的備援小時數
RAINFALL_HOURS_FALLBACK = (3, 6, 12, 24)

# 淹水 API（WRA Swagger）：region 為 taiwan/taoyuan/...；
# forecastHours：0=目前即時淹水範圍，1~6=未來預測 1~6 小時。
# 可用環境變數 INUNDATION_PARAMS（JSON）覆寫，例如 '{"region":"taoyuan","forecastHours":0}'。
INUNDATION_PARAMS: dict = json.loads(
    os.getenv("INUNDATION_PARAMS") or '{"region": "taoyuan", "forecastHours": 0}'
)

HTTP_TIMEOUT = (10, 60)  # (connect, read) seconds
HTTP_RETRIES = 3
USER_AGENT = "Taoyuan-Water-Monitor/1.1 (GitHub Actions)"

EXPECTED_DISTRICTS = 13

# 雨量色階對照：{(R, G, B): 代表雨量 mm}
# 必須依 WRA 官方色階填入並人工確認；留空時不會輸出任何雨量數值（寧缺勿錯）。
# 執行後請查看 data/latest/rainfall_statistics.json 的 color_histogram 取得實際出現的顏色。
RAINFALL_LEGEND: dict[tuple[int, int, int], float] = {}
COLOR_TOLERANCE = 12  # RGB 曼哈頓距離容許值
