# taoyuan-water-monitor

# 桃園市即時水情監測

水利署 rasterMap（雨量 1~24h、淹水 0~6h）＋ 氣象署 O-A0002-001（雨量觀測站）
→ GitHub Actions (Python) → 靜態 JSON/GeoJSON → GitHub Pages (Leaflet)

## 目錄
- `src/` ETL：`config` / `wra_client` / `cwa_client` / `stations` / `spatial` / `raster_processor` / `main`
- `data/boundary/taoyuan_districts.geojson` 行政區界（13 區）
- `web/` 前端（`index.html` + `style.css` + `app.js`）
- `.github/workflows/update.yml` 每 30 分鐘更新並直接部署（失敗則保留上一版）

## 啟用步驟
1. Settings → Pages → Source 選 **GitHub Actions**。
2. （選用）Settings → Secrets and variables → Actions → **New repository secret**：
   名稱 `CWA_API_KEY`，值為氣象開放資料平台會員授權碼。未設定時測站功能自動停用，其他功能不受影響。
   授權碼只在 ETL 執行時使用，不會寫入任何輸出檔、日誌或前端。
3. （選用）Variables 設定 `INUNDATION_PARAMS`（預設 `{"region":"taoyuan"}`）。
4. 手動執行一次 workflow（Actions → Run workflow）。

## 輸出（部署到網站 `data/`）
`district_status.json`、`stations.json`、`rainfall_h1~24.geojson`、`inundation_h0~6.geojson`、`taoyuan_districts.geojson`

## 本機
```bash
pip install -r requirements.txt
CWA_API_KEY=xxxx python src/main.py          # 授權碼可省略
mkdir -p _site/data && cp -r web/. _site/
cp data/boundary/*.geojson data/latest/*.json data/latest/*.geojson _site/data/
python -m http.server -d _site 8000
```

## 已知限制
- 雨量以級距呈現；1 小時圖的門檻是否與 24 小時圖相同，尚待 WRA 文件確認。
- 淹水判讀假設「非透明像素＝淹水」，尚待官方圖例確認。
- 測站警戒門檻（10 / 16 mm/h）為面板自訂值，非氣象署官方標準。
- 本站為自動彙整之參考資訊，非官方警戒或預警。
