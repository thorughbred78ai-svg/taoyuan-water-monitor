const map = L.map("map").setView([24.9937, 121.3010], 10);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

map.createPane("rain");   // 雨量網格（在行政區邊界下方）
map.getPane("rain").style.zIndex = 300;
map.createPane("flood");  // 淹水範圍
map.getPane("flood").style.zIndex = 450;

const STALE_HOURS = 4; // WRA 資料本身約延遲 2 小時

// ---- rain color scale ----
// v = 該色帶下限 mm；色碼取自氣象署累積雨量圖圖例，並與 WRA PNG 實際色票逐一比對
const SCALE = [
    { v: 0,   c: "#94a3b8" },
    { v: 1,   c: "#9dfdfe" },
    { v: 2,   c: "#01d2fd" },
    { v: 6,   c: "#00a5fe" },
    { v: 10,  c: "#0177fd" },
    { v: 15,  c: "#27a41c" },
    { v: 20,  c: "#01fa30" },
    { v: 30,  c: "#fefd31" },
    { v: 50,  c: "#ffa71f" },
    { v: 70,  c: "#ff2b06" },
    { v: 90,  c: "#d92203" },
    { v: 110, c: "#aa1800" },
    { v: 130, c: "#aa21a3" },
    { v: 150, c: "#dc2dd2" },
    { v: 200, c: "#ff38fb" },
    { v: 300, c: "#fed5fd" }
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
let selectedHour = 0;      // 淹水 forecastHours 0~6
let selectedRain = 1;      // 累積雨量延時 1~24
let districtLayer = null;
const rainLayer = L.layerGroup().addTo(map);
const floodLayer = L.layerGroup().addTo(map);
const markerLayer = L.layerGroup().addTo(map);
const alertLayer = L.layerGroup().addTo(map);
const floodCache = {};
const rainCache = {};

function rainOf(d, h = selectedRain) {
    return d?.rainfall?.[String(h)] ?? null;
}

function rainText(d) {
    const r = rainOf(d);
    if (!r || r.range === null || r.range === undefined) return "-";
    return `${r.range} mm${r.dry ? "（無雨推論）" : ""}`;
}

function alertCfg() {
    return status?.rainfall_alert ?? { hours: 1, mm: 60 };
}

function rainAlertOf(d) {
    if (selectedRain !== alertCfg().hours) return null;
    return rainOf(d)?.alert ?? null;
}

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

function showNotices(items) {
    const el = document.getElementById("notice");
    el.innerHTML = "";
    items.forEach(({ text, kind }) => {
        const div = document.createElement("div");
        div.className = `nmsg ${kind || "warn"}`;
        div.textContent = text;
        el.appendChild(div);
    });
    el.hidden = items.length === 0;
}

// ---- rendering ----
function popupHtml(name) {
    const d = statusMap[name];
    const f = floodOf(d);
    const a = rainAlertOf(d);
    const alertHtml = a
        ? `<br><span class="flood-badge">${a.level === "high" ? "⚠" : "△"} ` +
          `${esc(alertCfg().hours)} 小時雨量${a.level === "high" ? "超過" : "可能超過"} ${esc(alertCfg().mm)} mm` +
          `（${esc(a.range)} mm，${esc(a.cells)} 格 / ${esc(a.area_km2)} km²）</span>`
        : "";
    return `<strong>${esc(name)}</strong>` +
        `${isFlooded(d) ? ' <span class="flood-badge">⚠ 有淹水</span>' : ""}<br>` +
        `${selectedRain} 小時累積雨量（區內最高級距）：${esc(rainText(d))}${alertHtml}<br>` +
        `淹水面積（${esc(hourLabel(selectedHour))}）：${esc(fmt(f?.area_km2, "km²"))}`;
}

// 行政區只畫邊界（雨量由網格呈現）；有淹水者紅色粗虛線
function styleFor(feature) {
    const d = statusMap[districtName(feature.properties)];
    const flooded = isFlooded(d);
    return {
        color: flooded ? "#d00000" : "#334155",
        weight: flooded ? 4 : 1.5,
        dashArray: flooded ? "6 4" : null,
        fillColor: "#000000",
        fillOpacity: 0
    };
}

async function renderRain() {
    rainLayer.clearLayers();
    const key = String(selectedRain);
    if (!(key in rainCache)) {
        rainCache[key] = await loadOptionalJSON(`data/rainfall_h${key}.geojson`);
    }
    const gj = rainCache[key];
    const { hours, mm } = alertCfg();
    const alertOn = selectedRain === hours;
    if (gj && gj.features && gj.features.length) {
        L.geoJSON(gj, {
            pane: "rain",
            interactive: false,
            style: f => {
                const lo = f.properties.lo;
                const isAlert = alertOn && lo >= mm;
                return {
                    color: isAlert ? "#7f0000" : "#ffffff",
                    weight: isAlert ? 2.5 : 0,
                    stroke: isAlert,
                    fillColor: rainfallColor(lo),
                    fillOpacity: 0.78
                };
            }
        }).addTo(rainLayer);
    }
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

function renderAlerts() {
    alertLayer.clearLayers();
    districtLayer.eachLayer(lyr => {
        const name = districtName(lyr.feature.properties);
        const a = rainAlertOf(statusMap[name]);
        if (!a || !Array.isArray(a.center)) return;
        const high = a.level === "high";
        const text = `${high ? "⚠" : "△"} ${name} ${alertCfg().hours}h 雨量${high ? ">" : "可能>"}${alertCfg().mm} mm（${a.range}）`;
        L.marker(a.center, {
            icon: L.divIcon({
                className: "",
                html: `<div class="rain-marker ${high ? "high" : "possible"}">${esc(text)}</div>`,
                iconSize: null
            }),
            zIndexOffset: 1100,
            keyboard: false
        }).addTo(alertLayer).on("click", () => {
            map.setView(a.center, 13);
            lyr.openPopup(a.center);
        });
    });
}

function renderNotice() {
    const info = hourInfo[String(selectedHour)];
    const rinfo = status.rainfall_hours?.[String(selectedRain)];
    const dataTime = rinfo?.window_end || status.updated_at;
    const ageH = (Date.now() - new Date(dataTime).getTime()) / 3.6e6;
    const items = [];

    // 雨量警示
    const { hours, mm } = alertCfg();
    if (selectedRain === hours) {
        const high = status.districts.filter(d => rainAlertOf(d)?.level === "high");
        const poss = status.districts.filter(d => rainAlertOf(d)?.level === "possible");
        if (high.length) {
            items.push({
                kind: "rain",
                text: `⚠ ${hours} 小時累積雨量超過 ${mm} mm：` +
                    high.map(d => `${d.name}（${rainAlertOf(d).range} mm，${rainAlertOf(d).area_km2} km²）`).join("、")
            });
        }
        if (poss.length) {
            items.push({
                kind: "rain-possible",
                text: `△ ${hours} 小時累積雨量可能超過 ${mm} mm（級距跨越門檻）：` +
                    poss.map(d => `${d.name}（${rainAlertOf(d).range} mm）`).join("、")
            });
        }
    }

    // 淹水
    const flooded = status.districts.filter(d => isFlooded(d));
    if (info && !info.available) {
        items.push({ kind: "warn", text: `${hourLabel(selectedHour)}：目前無可用的淹水範圍資料，並不代表沒有淹水。` });
    } else if (flooded.length) {
        const isForecast = selectedHour !== 0;
        items.push({
            kind: isForecast ? "forecast" : "flood",
            text: `⚠ ${isForecast ? `預測 +${selectedHour} 小時` : "偵測到"}淹水範圍：` +
                flooded.map(d => `${d.name} ${floodOf(d).area_km2} km²`).join("、") +
                `（依水利署淹水範圍圖自動判讀${isForecast ? "，為模型預測" : ""}，僅供參考）`
        });
    }

    if (rinfo && !rinfo.available) {
        items.push({ kind: "warn", text: `${selectedRain} 小時累積雨量：目前無資料，請改選其他延時。` });
    } else if (ageH > STALE_HOURS) {
        items.push({ kind: "warn", text: `注意：資料已超過 ${STALE_HOURS} 小時未更新，請勿作為即時判斷依據。` });
    } else if (status.rainfall_legend_configured === false) {
        items.push({ kind: "warn", text: "雨量色階尚未校正，目前不顯示雨量數值。" });
    }
    showNotices(items);
}

function renderDistrictList() {
    const container = document.getElementById("district-list");
    container.innerHTML = "";
    const score = d => (rainAlertOf(d)?.level === "high" ? 2 : rainAlertOf(d) ? 1 : 0);
    [...status.districts]
        .sort((a, b) =>
            (isFlooded(b) - isFlooded(a)) ||
            (score(b) - score(a)) ||
            ((rainOf(b)?.mm ?? -1) - (rainOf(a)?.mm ?? -1)))
        .forEach(d => {
            const a = rainAlertOf(d);
            const el = document.createElement("div");
            el.className = "district" + (isFlooded(d) ? " flooded" : "") + (a ? " rain-alert" : "");
            el.innerHTML =
                `<div class="district-name">${esc(d.name)}` +
                `${isFlooded(d) ? '<span class="flood-badge">⚠ 有淹水</span>' : ""}` +
                `${a ? `<span class="flood-badge rain">${a.level === "high" ? "⚠" : "△"} 雨量&gt;${esc(alertCfg().mm)}</span>` : ""}</div>` +
                `<div class="district-value">${selectedRain} 小時累積雨量（區內最高級距）：${esc(rainText(d))}` +
                `<br>淹水面積（${esc(hourLabel(selectedHour))}）：${esc(fmt(floodOf(d)?.area_km2, "km²"))}</div>`;
            container.appendChild(el);
        });
}

async function renderHour() {
    districtLayer.setStyle(styleFor);
    renderMarkers();
    renderAlerts();
    renderNotice();
    renderDistrictList();
    await Promise.all([renderRain(), renderFlood()]);
}

// 雨量級距色帶（圖面型式：色塊由上而下為高→低，刻度標在色塊交界）
const LEGEND_BLOCKS = [
    "#fed5fd", "#ff38fb", "#dc2dd2", "#aa21a3", "#aa1800", "#d92203", "#ff2b06", "#ffa71f",
    "#fed428", "#fefd31", "#01fa30", "#27a41c", "#0177fd", "#00a5fe", "#01d2fd", "#9dfdfe", "#cacaca"
];
const LEGEND_TICKS = [300, 200, 150, 130, 110, 90, 70, 50, 40, 30, 20, 15, 10, 6, 2, 1];

function addLegend() {
    const legend = L.control({ position: "bottomleft" });
    legend.onAdd = () => {
        const div = L.DomUtil.create("div", "legend rain-legend");
        div.innerHTML =
            `<div class="rl-title">區內最高雨量級距<br>毫米(mm)</div>` +
            `<div class="rl-body">` +
              `<div class="rl-labels">` +
                LEGEND_TICKS.map((t, i) => `<span style="top:calc(var(--bh) * ${i + 1})">${t}</span>`).join("") +
              `</div>` +
              `<div class="rl-bar">` +
                LEGEND_BLOCKS.map(c => `<div style="background:${c}"></div>`).join("") +
              `</div>` +
            `</div>`;
        return div;
    };
    legend.addTo(map);
}

function updateWindowText() {
    const updated = document.getElementById("updated");
    const r = status.rainfall_hours?.[String(selectedRain)];
    updated.textContent = r?.available && r.window_start && r.window_end
        ? `雨量統計區間：${taipeiTime(r.window_start)} ～ ${taipeiTime(r.window_end)}`
        : `雨量統計區間：-`;
}

function setupSelects() {
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

    const rs = document.getElementById("rain-hours");
    rs.innerHTML = "";
    for (let h = 1; h <= 24; h++) {
        const info = status.rainfall_hours?.[String(h)];
        const opt = document.createElement("option");
        opt.value = String(h);
        opt.textContent = `${h} 小時` + (info && !info.available ? "（無資料）" : "");
        rs.appendChild(opt);
    }
    rs.disabled = false;
    rs.value = String(selectedRain);
    rs.addEventListener("change", () => {
        selectedRain = Number(rs.value);
        updateWindowText();
        renderHour();
    });
}

function startClock() {
    const el = document.getElementById("clock");
    const tick = () => {
        el.textContent = new Date().toLocaleString("zh-TW", {
            timeZone: "Asia/Taipei", hour12: false,
            year: "numeric", month: "2-digit", day: "2-digit",
            hour: "2-digit", minute: "2-digit", second: "2-digit"
        }) + " (臺灣)";
    };
    tick();
    setInterval(tick, 1000);
}

async function main() {
    startClock();
    const updated = document.getElementById("updated");
    try {
        const [boundary, st] = await Promise.all([
            loadJSON("data/taoyuan_districts.geojson"),
            loadJSON("data/district_status.json")
        ]);
        status = st;
        statusMap = Object.fromEntries(st.districts.map(d => [d.name, d]));
        hourInfo = st.inundation_hours ?? {};
        selectedRain = st.default_rainfall_hours ?? 1;

        districtLayer = L.geoJSON(boundary, {
            style: styleFor,
            onEachFeature: (f, lyr) => {
                lyr.bindPopup(() => popupHtml(districtName(f.properties)));
            }
        }).addTo(map);
        map.fitBounds(districtLayer.getBounds(), { padding: [20, 20] });

        addLegend();
        setupSelects();
        updateWindowText();
        await renderHour();
    } catch (error) {
        console.error(error);
        updated.textContent = "資料載入失敗，請稍後再試";
    }
}

main();
