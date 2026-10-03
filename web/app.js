const map = L.map("map").setView([24.9937, 121.3010], 10);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

map.createPane("flood");
map.getPane("flood").style.zIndex = 450;

const STALE_HOURS = 3;

function rainfallColor(mm) {
    if (mm === null || mm === undefined) return "#eeeeee";
    if (mm >= 200) return "#800026";
    if (mm >= 150) return "#BD0026";
    if (mm >= 100) return "#E31A1C";
    if (mm >= 80)  return "#FC4E2A";
    if (mm >= 50)  return "#FD8D3C";
    if (mm >= 30)  return "#FEB24C";
    if (mm >= 10)  return "#FED976";
    return "#FFFFCC";
}

function esc(value) {
    const d = document.createElement("div");
    d.textContent = String(value ?? "");
    return d.innerHTML;
}

function fmt(value, unit) {
    return value === null || value === undefined ? "-" : `${value} ${unit}`;
}

function rainText(d) {
    if (!d || d.rainfall_range === null || d.rainfall_range === undefined) return "-";
    return `${d.rainfall_range} mm${d.rainfall_dry_inferred ? "（無雨推論）" : ""}`;
}

function isFlooded(d) {
    return typeof d?.inundation_area_km2 === "number" && d.inundation_area_km2 > 0;
}

function taipeiTime(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    return isNaN(d) ? "-" : d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false });
}

async function loadJSON(path) {
    const r = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
}

async function loadOptionalJSON(path) {
    try { return await loadJSON(path); } catch { return null; }
}

function showNotice(text, flood = false) {
    const el = document.getElementById("notice");
    el.textContent = text;
    el.className = flood ? "flood" : "";
    el.hidden = false;
}

function districtName(props) {
    return props.TOWNNAME ?? props.townname ?? props.district ?? props["鄉鎮市區"];
}

function addLegend() {
    const legend = L.control({ position: "bottomleft" });
    legend.onAdd = () => {
        const div = L.DomUtil.create("div", "legend");
        div.innerHTML = "<i></i>淹水範圍／有淹水之行政區<br>底色：各區最高雨量級距";
        return div;
    };
    legend.addTo(map);
}

async function main() {
    const updated = document.getElementById("updated");
    try {
        const [boundary, status, floodGeo] = await Promise.all([
            loadJSON("data/taoyuan_districts.geojson"),
            loadJSON("data/district_status.json"),
            loadOptionalJSON("data/inundation.geojson")
        ]);

        const statusMap = Object.fromEntries(status.districts.map(d => [d.name, d]));
        const hours = status.cumulative_hours ?? 1;

        const layer = L.geoJSON(boundary, {
            style: f => {
                const d = statusMap[districtName(f.properties)];
                const flooded = isFlooded(d);
                return {
                    color: flooded ? "#d00000" : "#444",
                    weight: flooded ? 4 : 1,
                    dashArray: flooded ? "6 4" : null,
                    fillColor: rainfallColor(d?.rainfall_mm),
                    fillOpacity: 0.55
                };
            },
            onEachFeature: (f, lyr) => {
                const name = districtName(f.properties);
                const d = statusMap[name];
                lyr.bindPopup(
                    `<strong>${esc(name)}</strong>` +
                    `${isFlooded(d) ? ' <span class="flood-badge">⚠ 有淹水</span>' : ""}<br>` +
                    `${hours} 小時累積雨量（區內最高級距）：${esc(rainText(d))}<br>` +
                    `淹水面積：${esc(fmt(d?.inundation_area_km2, "km²"))}`
                );
            }
        }).addTo(map);
        map.fitBounds(layer.getBounds(), { padding: [20, 20] });

        // 淹水範圍（實際像素向量化）
        if (floodGeo && floodGeo.features && floodGeo.features.length) {
            L.geoJSON(floodGeo, {
                pane: "flood",
                style: { color: "#d00000", weight: 2, fillColor: "#ff0000", fillOpacity: 0.6 },
                interactive: false
            }).addTo(map);
        }

        // 有淹水的行政區：醒目標記
        const flooded = status.districts.filter(isFlooded);
        layer.eachLayer(lyr => {
            const name = districtName(lyr.feature.properties);
            const d = statusMap[name];
            if (!isFlooded(d)) return;
            L.marker(lyr.getBounds().getCenter(), {
                icon: L.divIcon({
                    className: "",
                    html: `<div class="flood-marker">⚠ ${esc(name)} 淹水 ${esc(d.inundation_area_km2)} km²</div>`,
                    iconSize: null
                }),
                zIndexOffset: 1000,
                keyboard: false
            }).addTo(map).on("click", () => lyr.openPopup());
        });

        addLegend();

        const dataTime = status.data_time || status.updated_at;
        updated.textContent = status.window_start && status.window_end
            ? `統計區間：${taipeiTime(status.window_start)} ～ ${taipeiTime(status.window_end)}（臺北時間）`
            : `資料時間：${taipeiTime(dataTime)}（臺北時間）`;

        const ageH = (Date.now() - new Date(dataTime).getTime()) / 3.6e6;
        if (flooded.length) {
            const text = flooded.map(d => `${d.name} ${d.inundation_area_km2} km²`).join("、");
            showNotice(`⚠ 偵測到淹水範圍：${text}（依水利署淹水範圍圖自動判讀，僅供參考）`, true);
        } else if (ageH > STALE_HOURS) {
            showNotice(`注意：資料已超過 ${STALE_HOURS} 小時未更新，請勿作為即時判斷依據。`);
        } else if (status.rainfall_legend_configured === false) {
            showNotice("雨量色階尚未校正，目前不顯示雨量數值。");
        } else if (status.inundation_available === false) {
            showNotice("目前無可用的淹水範圍資料，淹水面積顯示為「-」並不代表沒有淹水。");
        }

        renderDistrictList(status.districts, hours);
    } catch (error) {
        console.error(error);
        updated.textContent = "資料載入失敗，請稍後再試";
    }
}

function renderDistrictList(districts, hours) {
    const container = document.getElementById("district-list");
    container.innerHTML = "";
    [...districts]
        .sort((a, b) =>
            (isFlooded(b) - isFlooded(a)) ||
            ((b.rainfall_mm ?? -1) - (a.rainfall_mm ?? -1)))
        .forEach(d => {
            const el = document.createElement("div");
            el.className = "district" + (isFlooded(d) ? " flooded" : "");
            el.innerHTML =
                `<div class="district-name">${esc(d.name)}` +
                `${isFlooded(d) ? '<span class="flood-badge">⚠ 有淹水</span>' : ""}</div>` +
                `<div class="district-value">${hours} 小時累積雨量（區內最高級距）：${esc(rainText(d))}` +
                `<br>淹水面積：${esc(fmt(d.inundation_area_km2, "km²"))}</div>`;
            container.appendChild(el);
        });
}

main();
