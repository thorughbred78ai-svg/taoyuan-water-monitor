const map = L.map("map").setView([24.9937, 121.3010], 10);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

map.createPane("flood");
map.getPane("flood").style.zIndex = 450;

const STALE_HOURS = 4; // WRA 資料本身約延遲 2 小時

// ---- rain color scale ----
// v = 該色帶下限 mm；色碼取自氣象署累積雨量圖圖例，並與 WRA PNG 實際色票逐一比對
const SCALE = [
    { v: 0,   c: "#94a3b8", label: "<1（無雨）" },
    { v: 1,   c: "#9dfdfe", label: "1" },
    { v: 2,   c: "#01d2fd", label: "2" },
    { v: 6,   c: "#00a5fe", label: "6" },
    { v: 10,  c: "#0177fd", label: "10" },
    { v: 15,  c: "#27a41c", label: "15" },
    { v: 20,  c: "#01fa30", label: "20" },
    { v: 30,  c: "#fefd31", label: "30–50" },
    { v: 50,  c: "#ffa71f", label: "50" },
    { v: 70,  c: "#ff2b06", label: "70" },
    { v: 90,  c: "#d92203", label: "90" },
    { v: 110, c: "#aa1800", label: "110" },
    { v: 130, c: "#aa21a3", label: "130" },
    { v: 150, c: "#dc2dd2", label: "150" },
    { v: 200, c: "#ff38fb", label: "200" },
    { v: 300, c: "#fed5fd", label: "300+" }
];

function rainfallColor(mm) {
    if (mm === null || mm === undefined) return "#eeeeee";
    let c = SCALE[0].c;
    for (const s of SCALE) if (mm >= s.v) c = s.c;
    return c;
}

// ---- helpers ----
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

function districtName(props) {
    return props.TOWNNAME ?? props.townname ?? props.district ?? props["鄉鎮市區"];
}

// ---- state ----
let status = null;
let statusMap = {};
let hourInfo = {};
let selectedHour = 0;
let districtLayer = null;
const floodLayer = L.layerGroup().addTo(map);
const markerLayer = L.layerGroup().addTo(map);
const floodCache = {};

function floodOf(d, h = selectedHour) {
    return d?.inundation?.[String(h)] ?? null;
}

function isFlooded(d, h = selectedHour) {
    const f = floodOf(d, h);
    return typeof f?.area_km2 === "number" && f.area_km2 > 0;
}

function hourLabel(h) {
    return Number(h) === 0 ? "目前即時" : `預測 +${h} 小時`;
}

function showNotice(text, kind = "") {
    const el = document.getElementById("notice");
    el.textContent = text;
    el.className = kind;
    el.hidden = false;
}

function hideNotice() {
    document.getElementById("notice").hidden = true;
}

// ---- rendering ----
function popupHtml(name) {
    const d = statusMap[name];
    const f = floodOf(d);
    const hours = status.cumulative_hours ?? 1;
    return `<strong>${esc(name)}</strong>` +
        `${isFlooded(d) ? ' <span class="flood-badge">⚠ 有淹水</span>' : ""}<br>` +
        `${hours} 小時累積雨量（區內最高級距）：${esc(rainText(d))}<br>` +
        `淹水面積（${esc(hourLabel(selectedHour))}）：${esc(fmt(f?.area_km2, "km²"))}`;
}

function styleFor(feature) {
    const d = statusMap[districtName(feature.properties)];
    const flooded = isFlooded(d);
    return {
        color: flooded ? "#d00000" : "#444",
        weight: flooded ? 4 : 1,
        dashArray: flooded ? "6 4" : null,
        fillColor: rainfallColor(d?.rainfall_mm),
        fillOpacity: 0.55
    };
}

async function renderFlood() {
    floodLayer.clearLayers();
    const key = String(selectedHour);
    if (!(key in floodCache)) {
        floodCache[key] = await loadOptionalJSON(`data/inundation_h${key}.geojson`);
    }
    const gj = floodCache[key];
    if (gj && gj.features && gj.features.length) {
        L.geoJSON(gj, {
            pane: "flood",
            style: { color: "#d00000", weight: 2, fillColor: "#ff0000", fillOpacity: 0.6 },
            interactive: false
        }).addTo(floodLayer);
    }
}

function renderMarkers() {
    markerLayer.clearLayers();
    districtLayer.eachLayer(lyr => {
        const name = districtName(lyr.feature.properties);
        const d = statusMap[name];
        if (!isFlooded(d)) return;
        const f = floodOf(d);
        const pos = Array.isArray(f.center) ? f.center : lyr.getBounds().getCenter();
        const tag = selectedHour === 0 ? "淹水" : `預測+${selectedHour}h 淹水`;
        L.marker(pos, {
            icon: L.divIcon({
                className: "",
                html: `<div class="flood-marker">⚠ ${esc(name)} ${esc(tag)} ${esc(f.area_km2)} km²</div>`,
                iconSize: null
            }),
            zIndexOffset: 1000,
            keyboard: false
        }).addTo(markerLayer).on("click", () => {
            if (Array.isArray(f.center)) map.setView(f.center, 16);
            lyr.openPopup(pos);
        });
    });
}

function renderNotice() {
    const info = hourInfo[String(selectedHour)];
    const dataTime = status.data_time || status.updated_at;
    const ageH = (Date.now() - new Date(dataTime).getTime()) / 3.6e6;
    const flooded = status.districts.filter(d => isFlooded(d));

    if (info && !info.available) {
        showNotice(`${hourLabel(selectedHour)}：目前無可用的淹水範圍資料，並不代表沒有淹水。`);
    } else if (flooded.length) {
        const text = flooded.map(d => `${d.name} ${floodOf(d).area_km2} km²`).join("、");
        const isForecast = selectedHour !== 0;
        showNotice(
            `⚠ ${isForecast ? `預測 +${selectedHour} 小時` : "偵測到"}淹水範圍：${text}` +
            `（依水利署淹水範圍圖自動判讀${isForecast ? "，為模型預測" : ""}，僅供參考）`,
            isForecast ? "forecast" : "flood"
        );
    } else if (ageH > STALE_HOURS) {
        showNotice(`注意：資料已超過 ${STALE_HOURS} 小時未更新，請勿作為即時判斷依據。`);
    } else if (status.rainfall_legend_configured === false) {
        showNotice("雨量色階尚未校正，目前不顯示雨量數值。");
    } else {
        hideNotice();
    }
}

function renderDistrictList() {
    const container = document.getElementById("district-list");
    const hours = status.cumulative_hours ?? 1;
    container.innerHTML = "";
    [...status.districts]
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
                `<br>淹水面積（${esc(hourLabel(selectedHour))}）：${esc(fmt(floodOf(d)?.area_km2, "km²"))}</div>`;
            container.appendChild(el);
        });
}

async function renderHour() {
    districtLayer.setStyle(styleFor);
    renderMarkers();
    renderNotice();
    renderDistrictList();
    await renderFlood();
}

function addLegend() {
    const legend = L.control({ position: "bottomleft" });
    legend.onAdd = () => {
        const div = L.DomUtil.create("div", "legend");
        const rows = SCALE.map(s =>
            `<span class="row"><span class="sw" style="background:${s.c}"></span>${esc(s.label)}</span>`
        ).join(" ");
        div.innerHTML =
            `<strong>區內最高雨量級距 (mm)</strong><br>${rows}<br>` +
            `<i></i>淹水範圍／有淹水之行政區`;
        return div;
    };
    legend.addTo(map);
}

function setupHourSelect() {
    const sel = document.getElementById("hour");
    sel.innerHTML = "";
    for (let h = 0; h <= 6; h++) {
        const info = hourInfo[String(h)];
        const opt = document.createElement("option");
        opt.value = String(h);
        const when = info?.data_time ? `（${taipeiTime(info.data_time).slice(-8, -3)}）` : "";
        opt.textContent = hourLabel(h) + (info && !info.available ? "（無資料）" : when);
        sel.appendChild(opt);
    }
    sel.disabled = false;
    sel.value = "0";
    sel.addEventListener("change", () => {
        selectedHour = Number(sel.value);
        renderHour();
    });
}

async function main() {
    const updated = document.getElementById("updated");
    try {
        const [boundary, st] = await Promise.all([
            loadJSON("data/taoyuan_districts.geojson"),
            loadJSON("data/district_status.json")
        ]);
        status = st;
        statusMap = Object.fromEntries(st.districts.map(d => [d.name, d]));
        hourInfo = st.inundation_hours ?? {};

        districtLayer = L.geoJSON(boundary, {
            style: styleFor,
            onEachFeature: (f, lyr) => {
                lyr.bindPopup(() => popupHtml(districtName(f.properties)));
            }
        }).addTo(map);
        map.fitBounds(districtLayer.getBounds(), { padding: [20, 20] });

        addLegend();
        setupHourSelect();

        const dataTime = st.data_time || st.updated_at;
        updated.textContent = st.window_start && st.window_end
            ? `雨量統計區間：${taipeiTime(st.window_start)} ～ ${taipeiTime(st.window_end)}（臺北時間）`
            : `資料時間：${taipeiTime(dataTime)}（臺北時間）`;

        await renderHour();
    } catch (error) {
        console.error(error);
        updated.textContent = "資料載入失敗，請稍後再試";
    }
}

main();
