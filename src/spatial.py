import geopandas as gpd


def load_taoyuan():

    gdf = gpd.read_file(
        "data/boundary/taoyuan_districts.geojson"
    )

    return gdf

def overlay_inundation(
    districts,
    inundation
):

    districts = districts.to_crs(
        inundation.crs
    )

    result = gpd.overlay(
        districts,
        inundation,
        how="intersection"
    )

    return result

def calculate_area(gdf):

    metric = gdf.to_crs(
        "EPSG:3826"
    )

    metric["area_m2"] = (
        metric.geometry.area
    )

    metric["area_km2"] = (
        metric["area_m2"] / 1_000_000
    )

    return metric
