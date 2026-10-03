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

# 雨量色階（mm，區間 [lo, hi)；hi=None 表示以上）
# 來源：中央氣象署累積雨量圖圖例（2026-10-03 10:00 QZJ 圖，使用者提供截圖），
#       RGB 以圖例色塊取樣，並與 WRA PNG 實際出現的 15 種顏色逐一比對（誤差 <= 2）。
# 已知不確定：
#  - 圖例為氣象署產品，WRA 雨量圖採用相同色票，但「1 小時」圖是否同一組門檻尚未由 WRA 文件證實。
#  - PNG 出現兩種黃色 (254,253,49) 與 (255,253,40)，圖例只有 30-40 與 40-50 兩級且色票不完全相同，
#    無法確定兩者各對應哪一級，故合併為 30-50，不自行猜測。
RAINFALL_CLASSES: list[tuple[float, float | None, list[tuple[int, int, int]]]] = [
    (1, 2, [(157, 253, 254)]),
    (2, 6, [(1, 210, 253)]),
    (6, 10, [(0, 165, 254)]),
    (10, 15, [(1, 119, 253)]),
    (15, 20, [(39, 164, 28)]),
    (20, 30, [(1, 250, 48)]),
    (30, 50, [(254, 253, 49), (255, 253, 40)]),
    (50, 70, [(255, 167, 31)]),
    (70, 90, [(255, 43, 6)]),
    (90, 110, [(217, 34, 3)]),
    (110, 130, [(170, 24, 0)]),
    (130, 150, [(170, 33, 163)]),
    (150, 200, [(220, 45, 210)]),
    (200, 300, [(255, 56, 251)]),
    (300, None, [(254, 213, 253)]),
]
RAINFALL_LEGEND = bool(RAINFALL_CLASSES)

# 圖例最低級為灰色「<1 mm」；WRA PNG 中沒有出現灰色像素、無雨處為透明。
# True：該區完全沒有有色像素時，視為 "<1 mm"（推論，輸出會標示 dry_inferred）。
DRY_IF_TRANSPARENT = True
COLOR_TOLERANCE = 12  # RGB 曼哈頓距離容許值
