const map = L.map("map").setView(
    [24.9937, 121.3010],
    10
);


L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 18,
        attribution:
            "&copy; OpenStreetMap contributors"
    }
).addTo(map);


function rainfallColor(mm) {

    if (mm === null || mm === undefined) {
        return "#eeeeee";
    }

    if (mm >= 200) return "#800026";
    if (mm >= 150) return "#BD0026";
    if (mm >= 100) return "#E31A1C";
    if (mm >= 80)  return "#FC4E2A";
    if (mm >= 50)  return "#FD8D3C";
    if (mm >= 30)  return "#FEB24C";
    if (mm >= 10)  return "#FED976";

    return "#FFFFCC";
}


async function loadJSON(path) {

    const response =
        await fetch(
            path + "?t=" + Date.now()
        );

    if (!response.ok) {
        throw new Error(
            `HTTP ${response.status}`
        );
    }

    return response.json();
}


async function main() {

    try {

        const [
            boundary,
            status
        ] = await Promise.all([

            loadJSON(
                "../data/boundary/"
                + "taoyuan_districts.geojson"
            ),

            loadJSON(
                "../data/latest/"
                + "district_status.json"
            )
        ]);


        const statusMap = {};

        status.districts.forEach(
            district => {

                statusMap[
                    district.name
                ] = district;

            }
        );


        const layer =
            L.geoJSON(
                boundary,
                {

                    style: feature => {

                        const name =
                            feature.properties.TOWNNAME
                            ??
                            feature.properties.townname
                            ??
                            feature.properties.district
                            ??
                            feature.properties["鄉鎮市區"];

                        const district =
                            statusMap[name];

                        const rainfall =
                            district
                            ?.rainfall_mm;

                        return {

                            color: "#444",

                            weight: 1,

                            fillColor:
                                rainfallColor(
                                    rainfall
                                ),

                            fillOpacity: 0.55

                        };
                    },


                    onEachFeature:
                        (feature, layer) => {

                            const name =
                                feature.properties.TOWNNAME
                                ??
                                feature.properties.townname
                                ??
                                feature.properties.district
                                ??
                                feature.properties["鄉鎮市區"];

                            const district =
                                statusMap[name];


                            layer.bindPopup(`

                                <strong>
                                    ${name}
                                </strong>

                                <br>

                                累積雨量：
                                ${
                                    district
                                    ?.rainfall_mm
                                    ?? "-"
                                }
                                mm

                                <br>

                                淹水面積：
                                ${
                                    district
                                    ?.inundation_area_km2
                                    ?? "-"
                                }
                                km²

                            `);
                        }

                }
            );


        layer.addTo(map);


        map.fitBounds(
            layer.getBounds(),
            {
                padding: [20, 20]
            }
        );


        document.getElementById(
            "updated"
        ).textContent =
            "資料更新時間："
            + status.updated_at;


        renderDistrictList(
            status.districts
        );


    } catch (error) {

        console.error(error);

        document.getElementById(
            "updated"
        ).textContent =
            "資料載入失敗";

    }
}


function renderDistrictList(
    districts
) {

    const container =
        document.getElementById(
            "district-list"
        );


    container.innerHTML = "";


    districts
        .sort(
            (a, b) =>
                (b.rainfall_mm ?? -1)
                -
                (a.rainfall_mm ?? -1)
        )
        .forEach(
            district => {

                const element =
                    document.createElement(
                        "div"
                    );

                element.className =
                    "district";


                element.innerHTML = `

                    <div class="district-name">
                        ${district.name}
                    </div>

                    <div class="district-value">

                        累積雨量：
                        ${
                            district.rainfall_mm
                            ?? "-"
                        }
                        mm

                        <br>

                        淹水面積：
                        ${
                            district.inundation_area_km2
                            ?? "-"
                        }
                        km²

                    </div>

                `;


                container.appendChild(
                    element
                );

            }
        );
}


main();
