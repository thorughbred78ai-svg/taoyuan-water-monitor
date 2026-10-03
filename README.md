# taoyuan-water-monitor

# 桃園市即時水情監測

水利署開放資料 (WRA rasterMap) → GitHub Actions (Python/Rasterio/GeoPandas) → 行政區統計 → GitHub Pages (Leaflet)

## 目錄
- `src/` ETL（config / wra_client / spatial / raster_processor / main）
- `data/boundary/taoyuan_districts.geojson` 行政區界（內政部國土測繪中心，13 區）
- `web/` 前端；部署時 workflow 會把 `data/boundary` 與 `district_status.json` 複製到網站根目錄 `data/`
- `.github/workflows/update.yml` 每 30 分鐘更新並直接部署（失敗則保留上一版）

## 啟用
1. Settings → Pages → Source 選 **GitHub Actions**
2. 刪除舊的 `pages.yml`、`data/latest/district_status.json`（範例假資料）
3. 手動執行一次 workflow，打開 `rainfall_statistics.json` 的 `color_histogram`，對照 WRA 官方色階，填入 `src/config.py` 的 `RAINFALL_LEGEND`

## 本機
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
mkdir -p _site/data && cp -r web/. _site/ && cp data/boundary/*.geojson data/latest/district_status.json _site/data/
python -m http.server -d _site 8000
```
