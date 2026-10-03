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

# 雨量 API：cumulativeHours 為 1~24 的整數（Swagger）；一次下載 1~24 全部延時
RAINFALL_HOURS: tuple[int, ...] = tuple(range(1, 25))
RAINFALL_WORKERS = 4  # 併發下載數（對公共 API 保持禮貌）

# 淹水 API（WRA Swagger）：region 為 taiwan/taoyuan/...；
# forecastHours：0=目前即時淹水範圍，1~6=未來預測 1~6 小時。程式會逐一抓取 0~6。
# 可用環境變數 INUNDATION_PARAMS（JSON）覆寫 region 等固定參數；forecastHours 由程式帶入。
INUNDATION_PARAMS: dict = json.loads(os.getenv("INUNDATION_PARAMS") or '{"region": "taoyuan"}')
INUNDATION_PARAMS.pop("forecastHours", None)
INUNDATION_HOURS: tuple[int, ...] = tuple(range(0, 7))

# 中央氣象署開放資料：O-A0002-001 雨量觀測站－雨量資料
# 授權碼放在 GitHub Repository secret `CWA_API_KEY`（Settings → Secrets and variables → Actions）；
# 未設定時測站功能自動停用，不影響 WRA 雨量/淹水。
CWA_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
CWA_API_KEY = os.getenv("CWA_API_KEY", "").strip()
CWA_COUNTY = "桃園市"

# 桃園市政府資料開放平台：路面淹水感測器即時資訊（無需授權碼）
ROAD_SENSOR_URL = ("https://opendata.tycg.gov.tw/api/v1/dataset.api_access"
                   "?rid=b57a725d-1ac5-41ff-9256-bfda414092df&format=json")
# height 超過此值即在地圖示警（使用者指定；來源資料未標示單位，請對照資料集說明）
ROAD_SENSOR_ALERT_HEIGHT = float(os.getenv("ROAD_SENSOR_ALERT_HEIGHT", "15"))

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

# 雨量警示：僅針對「指定延時」(預設 1 小時) 檢查是否超過門檻 (預設 60 mm)。
# 雨量以級距表示，故分兩級：
#   high     = 級距下限 >= 門檻（確定超過，例：70–90）
#   possible = 門檻落在級距內部（可能超過，例：50–70 含 60）
RAINFALL_ALERT_HOURS = 1
RAINFALL_ALERT_MM = 60.0
COLOR_TOLERANCE = 12  # RGB 曼哈頓距離容許值
