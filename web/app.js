const map = L.map("map").setView([24.9937, 121.3010], 10);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

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

function showNotice(text) {
    const el = document.getElementById("notice");
    el.textContent = text;
    el.hidden = false;
}

function districtName(props) {
    return props.TOWNNAME ?? props.townname ?? props.district ?? props["鄉鎮市區"];
}

async function main() {
    const updated = document.getElementById("updated");
    try {
        const [boundary, status] = await Promise.all([
            loadJSON("data/taoyuan_districts.geojson"),
            loadJSON("data/district_status.json")
        ]);

        const statusMap = Object.fromEntries(status.districts.map(d => [d.name, d]));
        const hours = status.cumulative_hours ?? 1;

        const layer = L.geoJSON(boundary, {
            style: f => ({
                color: "#444",
                weight: 1,
                fillColor: rainfallColor(statusMap[districtName(f.properties)]?.rainfall_mm),
                fillOpacity: 0.55
            }),
            onEachFeature: (f, lyr) => {
                const name = districtName(f.properties);
                const d = statusMap[name];
                lyr.bindPopup(
                    `<strong>${esc(name)}</strong><br>` +
                    `${hours} 小時累積雨量（最大）：${esc(fmt(d?.rainfall_mm, "mm"))}<br>` +
                    `淹水面積：${esc(fmt(d?.inundation_area_km2, "km²"))}`
                );
            }
        }).addTo(map);
        map.fitBounds(layer.getBounds(), { padding: [20, 20] });

        const dataTime = status.data_time || status.updated_at;
        updated.textContent = `資料時間：${taipeiTime(dataTime)}（臺北時間）`;

        const ageH = (Date.now() - new Date(dataTime).getTime()) / 3.6e6;
        if (ageH > STALE_HOURS) {
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
        .sort((a, b) => (b.rainfall_mm ?? -1) - (a.rainfall_mm ?? -1))
        .forEach(d => {
            const el = document.createElement("div");
            el.className = "district";
            el.innerHTML =
                `<div class="district-name">${esc(d.name)}</div>` +
                `<div class="district-value">${hours} 小時累積雨量（最大）：${esc(fmt(d.rainfall_mm, "mm"))}` +
                `<br>平均：${esc(fmt(d.rainfall_mean_mm, "mm"))}` +
                `<br>淹水面積：${esc(fmt(d.inundation_area_km2, "km²"))}</div>`;
            container.appendChild(el);
        });
}

main();
