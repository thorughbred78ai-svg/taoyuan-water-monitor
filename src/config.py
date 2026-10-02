WRA_BASE_URL = "https://iot.wra.gov.tw"

PRECIPITATION_API = (
    f"{WRA_BASE_URL}/rasterMap/precipitation"
)

INUNDATION_API = (
    f"{WRA_BASE_URL}/rasterMap/inundation"
)

PRECIPITATION_METADATA_API = (
    f"{WRA_BASE_URL}/rasterMap/precipitation/rasterMapMetaData"
)

INUNDATION_METADATA_API = (
    f"{WRA_BASE_URL}/rasterMap/inundation/rasetMapMetaData"
)

# 桃園市 approximate bbox
TAOYUAN_BBOX = {
    "min_lon": 120.95,
    "min_lat": 24.75,
    "max_lon": 121.45,
    "max_lat": 25.15,
}

OUTPUT_DIR = "data/latest"
BOUNDARY_FILE = "data/boundary/taoyuan_districts.geojson"
