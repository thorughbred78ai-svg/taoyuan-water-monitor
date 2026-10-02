# taoyuan-water-monitor
# 桃園市即時水情監測

使用水利署水文開放資料 API，
定期取得桃園市相關水文資料，
並透過 GitHub Actions 執行 ETL。

## Architecture

WRA API
↓
GitHub Actions
↓
Python
↓
GDAL / Rasterio / GeoPandas
↓
Taoyuan boundary
↓
GeoJSON / JSON
↓
Leaflet
↓
GitHub Pages

## Data sources

### Water Resources Agency

- Real-time accumulated precipitation
- Real-time inundation extent

API:

https://iot.wra.gov.tw/swagger/index.html

### Administrative boundary

National Land Surveying and Mapping Center

https://data.gov.tw/dataset/7441

## Local development

```bash
python -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

python src/main.py

