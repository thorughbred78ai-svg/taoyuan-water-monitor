"use strict";

/* =====================================================
   設定
===================================================== */
const REFRESH_OPTIONS = [5, 10, 30, 60];   // 分鐘；預設 30
const REFRESH_DEFAULT = 30;
const STALE_HOURS = 4;        // WRA 資料本身約延遲 2 小時
// 測站警戒門檻：面板自訂，非氣象署官方標準，請依業務需求調整
const STATION_THRESHOLDS = { warning: 10, danger: 16 };   // 1 小時雨量 mm

// 雨量色階：v = 級距下限 mm；色碼取自氣象署累積雨量圖圖例並與 WRA PNG 實際色票比對
const SCALE = [
    { v: 0,   c: "#94a3b8" }, { v: 1,   c: "#9dfdfe" }, { v: 2,   c: "#01d2fd" },
    { v: 6,   c: "#00a5fe" }, { v: 10,  c: "#0177fd" }, { v: 15,  c: "#27a41c" },
    { v: 20,  c: "#01fa30" }, { v: 30,  c: "#fefd31" }, { v: 50,  c: "#ffa71f" },
    { v: 70,  c: "#ff2b06" }, { v: 90,  c: "#d92203" }, { v: 110, c: "#aa1800" },
    { v: 130, c: "#aa21a3" }, { v: 150, c: "#dc2dd2" }, { v: 200, c: "#ff38fb" },
    { v: 300, c: "#fed5fd" }
];
const LEGEND_BLOCKS = [
    "#fed5fd", "#ff38fb", "#dc2dd2", "#aa21a3", "#aa1800", "#d92203", "#ff2b06", "#ffa71f",
    "#fed428", "#fefd31", "#01fa30", "#27a41c", "#0177fd", "#00a5fe", "#01d2fd", "#9dfdfe", "#cacaca"
];
const LEGEND_TICKS = [300, 200, 150, 130, 110, 90, 70, 50, 40, 30, 20, 15, 10, 6, 2, 1];

function rainfallColor(mm) {
    if (mm === null || mm === undefined) return "#cbd5e1";
    let c = SCALE[0].c;
    for (const s of SCALE) if (mm >= s.v) c = s.c;
    return c;
}

/* =====================================================
   工具
===================================================== */
const $ = id => document.getElementById(id);

function esc(value) {
    const d = document.createElement("div");
    d.textContent = String(value ?? "");
    return d.innerHTML;
}

function mmText(v) {
    return v === null || v === undefined ? "-" : `${Number(v).toFixed(1)} mm`;
}

function fmt(value, unit) {
    return value === null || value === undefined ? "-" : `${value} ${unit}`;
}

function twTime(iso, withDate = true) {
    if (!iso) return "-";
    const d = new Date(iso);
    if (isNaN(d)) return "-";
    return d.toLocaleString("zh-TW", {
        timeZone: "Asia/Taipei", hour12: false,
        ...(withDate ? { month: "2-digit", day: "2-digit" } : {}),
        hour: "2-digit", minute: "2-digit"
    });
}

async function loadJSON(path) {
    const r = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
}
async function loadOptionalJSON(path) {
    try { return await loadJSON(path); } catch { return null; }
}

const districtName = p => p.TOWNNAME ?? p.townname ?? p.district ?? p["鄉鎮市區"];

/* =====================================================
   狀態
===================================================== */
let status = null, stationData = null, stations = [];
let roadData = null, roadSensors = [];
let currentSig = "", refreshMin = REFRESH_DEFAULT, nextAt = 0, lastCheck = null, lastResult = "", reloading = false;
let statusMap = {}, hourInfo = {};
let selectedRain = 1, selectedFlood = 0;
let districtLayer = null;
const districtByName = {};
const stationMarkers = {};
const rainCache = {}, floodCache = {};

/* =====================================================
   地圖
===================================================== */
const map = L.map("map", { zoomControl: true }).setView([24.94, 121.25], 10);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "© OpenStreetMap contributors"
}).addTo(map);

map.createPane("rain");  map.getPane("rain").style.zIndex = 300;   // 雨量網格（邊界之下）
map.createPane("flood"); map.getPane("flood").style.zIndex = 450;

const rainLayer = L.layerGroup().addTo(map);
const stationLayer = L.layerGroup().addTo(map);
const roadLayer = L.layerGroup().addTo(map);       // 一般感測點（可勾選）
const roadAlertLayer = L.layerGroup().addTo(map);  // 超過門檻的示警（不受勾選影響）
const floodLayer = L.layerGroup().addTo(map);
const floodMarkerLayer = L.layerGroup().addTo(map);
const rainAlertLayer = L.layerGroup().addTo(map);

L.control.layers(null, {
    "雨量網格（水利署）": rainLayer,
    "雨量測站（氣象署）": stationLayer,
    "路面淹水感測器": roadLayer,
    "淹水範圍": floodLayer
}, { collapsed: true, position: "topright" }).addTo(map);

function addLegend() {
    const box = map.getContainer();
    const div = document.createElement("div");
    div.className = "legend rain-legend map-legend";
    div.innerHTML =
        `<div class="rl-head" tabindex="0" role="group" aria-label="雨量圖例；可拖曳或用方向鍵移動，雙擊或按 Home 重置位置" title="拖曳移動／雙擊重置位置">` +
          `<span class="rl-grip" aria-hidden="true">⠿</span>` +
          `<span class="rl-title">區內最高雨量級距<br>毫米(mm)</span>` +
          `<button class="rl-toggle" type="button" aria-label="收合或展開圖例">−</button>` +
        `</div>` +
        `<div class="rl-body"><div class="rl-labels">` +
        LEGEND_TICKS.map((t, i) => `<span style="top:calc(var(--bh) * ${i + 1})">${t}</span>`).join("") +
        `</div><div class="rl-bar">` +
        LEGEND_BLOCKS.map(c => `<div style="background:${c}"></div>`).join("") +
        `</div></div>`;
    box.appendChild(div);
    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);

    const head = div.querySelector(".rl-head");
    const toggle = div.querySelector(".rl-toggle");
    const KEY = "taoyuan-water-legend";
    let moved = false;

    const clamp = (x, y) => {
        const bw = box.clientWidth - div.offsetWidth, bh = box.clientHeight - div.offsetHeight;
        return [Math.min(Math.max(x, 0), Math.max(bw, 0)), Math.min(Math.max(y, 0), Math.max(bh, 0))];
    };
    const place = (x, y) => {
        [x, y] = clamp(x, y);
        div.classList.add("moved");
        div.style.left = x + "px"; div.style.top = y + "px";
        moved = true;
    };
    const save = () => {
        const bw = Math.max(box.clientWidth - div.offsetWidth, 1), bh = Math.max(box.clientHeight - div.offsetHeight, 1);
        try { localStorage.setItem(KEY, JSON.stringify({ fx: div.offsetLeft / bw, fy: div.offsetTop / bh })); } catch { /* ignore */ }
    };
    const reset = () => {
        moved = false;
        div.classList.remove("moved");
        div.style.left = div.style.top = "";
        try { localStorage.removeItem(KEY); } catch { /* ignore */ }
    };
    const restore = () => {
        try {
            const v = JSON.parse(localStorage.getItem(KEY) || "null");
            if (v) place(v.fx * (box.clientWidth - div.offsetWidth), v.fy * (box.clientHeight - div.offsetHeight));
        } catch { /* ignore */ }
    };
    const setCollapsed = c => {
        div.classList.toggle("collapsed", c);
        toggle.textContent = c ? "+" : "−";
        if (moved) place(div.offsetLeft, div.offsetTop);
    };

    // 拖曳（滑鼠/觸控/手寫筆）
    let drag = null;
    head.addEventListener("pointerdown", e => {
        if (e.target.closest(".rl-toggle")) return;
        const r = div.getBoundingClientRect(), b = box.getBoundingClientRect();
        drag = { dx: e.clientX - r.left, dy: e.clientY - r.top, bx: b.left, by: b.top };
        head.setPointerCapture(e.pointerId);
        div.classList.add("dragging");
        e.preventDefault();
    });
    head.addEventListener("pointermove", e => {
        if (!drag) return;
        place(e.clientX - drag.bx - drag.dx, e.clientY - drag.by - drag.dy);
    });
    const end = e => {
        if (!drag) return;
        drag = null; div.classList.remove("dragging");
        try { head.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
        save();
    };
    head.addEventListener("pointerup", end);
    head.addEventListener("pointercancel", end);
    head.addEventListener("dblclick", e => { if (!e.target.closest(".rl-toggle")) reset(); });

    // 鍵盤：方向鍵移動、Home 重置、Enter/空白 收合
    head.addEventListener("keydown", e => {
        const step = e.shiftKey ? 40 : 12;
        const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
        if (d) {
            e.preventDefault();
            place(div.offsetLeft + d[0], div.offsetTop + d[1]); save();
        } else if (e.key === "Home") { e.preventDefault(); reset(); }
        else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setCollapsed(!div.classList.contains("collapsed")); }
    });
    toggle.addEventListener("click", () => setCollapsed(!div.classList.contains("collapsed")));

    // 視窗/容器縮放時維持在範圍內
    new ResizeObserver(() => { if (moved) { place(div.offsetLeft, div.offsetTop); } }).observe(box);

    if (box.clientWidth < 520) setCollapsed(true);   // 手機預設收合，避免遮住地圖
    restore();
}

/* =====================================================
   資料存取（單一來源，避免各處重複判斷）
===================================================== */
const alertCfg = () => status?.rainfall_alert ?? { hours: 1, mm: 60 };
const rainOf = (d, h = selectedRain) => d?.rainfall?.[String(h)] ?? null;
const floodOf = (d, h = selectedFlood) => d?.inundation?.[String(h)] ?? null;
const isFlooded = (d, h = selectedFlood) => (floodOf(d, h)?.area_km2 ?? 0) > 0;
const rainAlertOf = d => selectedRain === alertCfg().hours ? (rainOf(d)?.alert ?? null) : null;
const floodLabel = h => Number(h) === 0 ? "目前即時" : `預測 +${h} 小時`;
const r1 = s => s.rain?.past1hr ?? null;
const r24 = s => s.rain?.past24hr ?? null;

function rainText(d) {
    const r = rainOf(d);
    if (!r || r.range == null) return "-";
    return `${r.range} mm${r.dry ? "（無雨推論）" : ""}`;
}

function maxOf(list, fn) {
    const v = list.map(fn).filter(x => typeof x === "number");
    return v.length ? Math.max(...v) : null;
}

/* =====================================================
   測站（氣象署 O-A0002-001）
===================================================== */
function stationPopup(s) {
    const x = s.rain || {};
    return `<strong>${esc(s.name)}測站</strong><br>` +
        `行政區：${esc(s.district ?? "-")}　代碼：${esc(s.id)}<br>` +
        `觀測時間：${esc(twTime(s.obs_time))}<br>` +
        `即時：${esc(mmText(x.now))}<br>` +
        `10 分鐘：${esc(mmText(x.past10min))}<br>` +
        `1 小時：${esc(mmText(x.past1hr))}<br>` +
        `3 小時：${esc(mmText(x.past3hr))}<br>` +
        `24 小時：${esc(mmText(x.past24hr))}`;
}

function renderStationMarkers() {
    stationLayer.clearLayers();
    stations.forEach(s => {
        const icon = L.divIcon({
            className: "",
            html: `<div style="width:16px;height:16px;border-radius:50%;background:${rainfallColor(r1(s))};` +
                  `border:3px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.4)"></div>`,
            iconSize: [16, 16], iconAnchor: [8, 8]
        });
        const m = L.marker([s.lat, s.lng], { icon, title: `${s.name} ${mmText(r1(s))}` })
            .bindPopup(() => stationPopup(s));
        m.addTo(stationLayer);
        stationMarkers[s.id] = m;
    });
}

function renderKPI() {
    const ok = stations.length > 0;
    $("max1h").textContent = ok && maxOf(stations, r1) !== null ? maxOf(stations, r1).toFixed(1) : "--";
    $("max24h").textContent = ok && maxOf(stations, r24) !== null ? maxOf(stations, r24).toFixed(1) : "--";
    $("wetCount").textContent = ok ? stations.filter(s => (r1(s) ?? 0) > 0).length : "--";
    $("stationCount").textContent = ok ? stations.length : "--";
}

/* =====================================================
   路面淹水感測器（桃園市政府資料開放平台）
===================================================== */
const roadThreshold = () => roadData?.alert_height ?? 15;
const isRoadAlert = s => typeof s.height === "number" && s.height > roadThreshold();

function roadPopup(s) {
    return `<strong>${esc(s.name)}</strong>` +
        `${isRoadAlert(s) ? ' <span class="badge">⚠ 超過 ' + esc(roadThreshold()) + '</span>' : ""}<br>` +
        `地點：${esc(s.address ?? "-")}<br>` +
        `行政區：${esc(s.district ?? "-")}　代碼：${esc(s.id)}<br>` +
        `高度（height）：<strong>${esc(s.height ?? "-")}</strong>（單位依資料集定義）<br>` +
        `資料時間：${esc(twTime(s.data_time))}`;
}

function renderRoad() {
    roadLayer.clearLayers();
    roadAlertLayer.clearLayers();
    roadSensors.forEach(s => {
        const alert = isRoadAlert(s);
        const wet = typeof s.height === "number" && s.height > 0;
        const cls = alert ? "alert" : wet ? "wet" : s.height == null ? "na" : "";
        const size = alert ? 20 : 16;
        const marker = L.marker([s.lat, s.lng], {
            icon: L.divIcon({ className: "", html: `<div class="rs-dot ${cls}"></div>`,
                              iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
            zIndexOffset: alert ? 900 : 0,
            title: `${s.name} 高度 ${s.height ?? "-"}`
        }).bindPopup(() => roadPopup(s));
        if (alert) {
            marker.addTo(roadAlertLayer);
            labelMarker([s.lat, s.lng], "rain-marker high road",
                `⚠ 路面淹水 ${s.name} 高度 ${s.height}`,
                () => map.setView([s.lat, s.lng], 16)).addTo(roadAlertLayer);
        } else {
            marker.addTo(roadLayer);
        }
    });
}

function stationsDisabledNote() {
    const reason = stationData?.reason ? `（${stationData.reason}）` : "";
    return `<div class="empty-note">氣象署測站資料未啟用${esc(reason)}<br>請於 Repository secrets 設定 CWA_API_KEY。</div>`;
}

function renderRanking() {
    const box = $("rankList");
    if (!stations.length) { box.innerHTML = stationsDisabledNote(); return; }
    const sorted = [...stations].sort((a, b) => (r1(b) ?? -1) - (r1(a) ?? -1));
    box.innerHTML = sorted.map((s, i) => `
        <div class="rank-item">
          <div class="rank-no">${i + 1}</div>
          <div><div class="rank-name">${esc(s.name)}測站</div><div class="rank-sub">${esc(s.district ?? "-")}</div></div>
          <div class="rank-value">${esc(mmText(r1(s)))}</div>
        </div>`).join("");
}

function renderStationList(keyword = "") {
    const box = $("stationList");
    if (!stations.length) { box.innerHTML = ""; return; }
    const list = stations.filter(s => `${s.name}${s.district ?? ""}${s.id}`.includes(keyword));
    box.innerHTML = list.map(s => `
        <div class="station" data-id="${esc(s.id)}">
          <div class="station-top">
            <span class="station-name">${esc(s.name)}測站</span>
            <span class="station-value" style="color:${rainfallColor(r1(s))}">${esc(mmText(r1(s)))}</span>
          </div>
          <div class="station-meta">${esc(s.district ?? "-")} ／ ${esc(s.id)} ／ 24H ${esc(mmText(r24(s)))}</div>
        </div>`).join("") || `<div class="empty-note">沒有符合的測站</div>`;
    box.querySelectorAll(".station").forEach(el => el.addEventListener("click", () => {
        const s = stations.find(x => String(x.id) === el.dataset.id);
        const m = s && stationMarkers[s.id];
        if (m) { map.setView([s.lat, s.lng], 14); m.openPopup(); }
    }));
}

/* =====================================================
   地圖圖層：行政區 / 雨量網格 / 淹水 / 警示標籤
===================================================== */
function popupHtml(name) {
    const d = statusMap[name], f = floodOf(d), a = rainAlertOf(d);
    const alertHtml = a
        ? `<br><span class="badge rain">${a.level === "high" ? "⚠" : "△"} ${esc(alertCfg().hours)} 小時雨量` +
          `${a.level === "high" ? "超過" : "可能超過"} ${esc(alertCfg().mm)} mm（${esc(a.range)} mm，${esc(a.cells)} 格 / ${esc(a.area_km2)} km²）</span>`
        : "";
    const st = stations.filter(s => s.district === name);
    const stHtml = st.length ? `<br>測站最大 1H / 24H：${esc(mmText(maxOf(st, r1)))} / ${esc(mmText(maxOf(st, r24)))}` : "";
    const ra = roadSensors.filter(x => x.district === name && isRoadAlert(x));
    const roadHtml = ra.length ? `<br><span class="badge">⚠ 路面淹水感測器示警 ${ra.length} 處</span>` : "";
    return `<strong>${esc(name)}</strong>${isFlooded(d) ? ' <span class="badge">⚠ 有淹水</span>' : ""}${roadHtml}<br>` +
        `${selectedRain} 小時累積雨量（區內最高級距）：${esc(rainText(d))}${alertHtml}${stHtml}<br>` +
        `淹水面積（${esc(floodLabel(selectedFlood))}）：${esc(fmt(f?.area_km2, "km²"))}`;
}

function styleFor(feature) {
    const flooded = isFlooded(statusMap[districtName(feature.properties)]);
    return {
        color: flooded ? "#d00000" : "#334155", weight: flooded ? 4 : 1.5,
        dashArray: flooded ? "6 4" : null, fillColor: "#000", fillOpacity: 0
    };
}

async function renderRain() {
    rainLayer.clearLayers();
    const key = String(selectedRain);
    if (!(key in rainCache)) rainCache[key] = await loadOptionalJSON(`data/rainfall_h${key}.geojson`);
    const gj = rainCache[key];
    const { hours, mm } = alertCfg();
    if (gj?.features?.length) {
        L.geoJSON(gj, {
            pane: "rain", interactive: false,
            style: f => {
                const isAlert = selectedRain === hours && f.properties.lo >= mm;
                return {
                    color: "#7f0000", stroke: isAlert, weight: isAlert ? 2.5 : 0,
                    fillColor: rainfallColor(f.properties.lo), fillOpacity: 0.72
                };
            }
        }).addTo(rainLayer);
    }
}

async function renderFlood() {
    floodLayer.clearLayers();
    const key = String(selectedFlood);
    if (!(key in floodCache)) floodCache[key] = await loadOptionalJSON(`data/inundation_h${key}.geojson`);
    const gj = floodCache[key];
    if (gj?.features?.length) {
        L.geoJSON(gj, {
            pane: "flood", interactive: false,
            style: { color: "#d00000", weight: 2, fillColor: "#ff0000", fillOpacity: 0.6 }
        }).addTo(floodLayer);
    }
}

function labelMarker(pos, cls, text, onClick) {
    return L.marker(pos, {
        icon: L.divIcon({ className: "", html: `<div class="${cls}">${esc(text)}</div>`, iconSize: null }),
        zIndexOffset: 1000, keyboard: false
    }).on("click", onClick);
}

function renderFloodMarkers() {
    floodMarkerLayer.clearLayers();
    status.districts.filter(d => isFlooded(d)).forEach(d => {
        const f = floodOf(d), lyr = districtByName[d.name];
        const pos = Array.isArray(f.center) ? f.center : lyr.getBounds().getCenter();
        const tag = selectedFlood === 0 ? "淹水" : `預測+${selectedFlood}h 淹水`;
        labelMarker(pos, "flood-marker", `⚠ ${d.name} ${tag} ${f.area_km2} km²`, () => {
            if (Array.isArray(f.center)) map.setView(f.center, 16);
            lyr.openPopup(pos);
        }).addTo(floodMarkerLayer);
    });
}

function renderRainAlertMarkers() {
    rainAlertLayer.clearLayers();
    status.districts.forEach(d => {
        const a = rainAlertOf(d);
        if (!a || !Array.isArray(a.center)) return;
        const high = a.level === "high", { hours, mm } = alertCfg();
        labelMarker(a.center, `rain-marker ${high ? "high" : "possible"}`,
            `${high ? "⚠" : "△"} ${d.name} ${hours}h 雨量${high ? ">" : "可能>"}${mm} mm（${a.range}）`,
            () => { map.setView(a.center, 13); districtByName[d.name].openPopup(a.center); }
        ).addTo(rainAlertLayer);
    });
}

/* =====================================================
   提示列 / 警戒 / 系統狀態
===================================================== */
function dataState() {
    const rinfo = status.rainfall_hours?.[String(selectedRain)];
    const end = rinfo?.window_end || status.updated_at;
    const ageH = (Date.now() - new Date(end).getTime()) / 3.6e6;
    if (rinfo && !rinfo.available) return { key: "stale", text: "雨量資料缺失", color: "var(--err)" };
    if (ageH > STALE_HOURS) return { key: "stale", text: "資料過期", color: "var(--err)" };
    if (!stations.length) return { key: "partial", text: "部分資料（測站未啟用）", color: "var(--run)" };
    return { key: "ok", text: "正常", color: "var(--ok)" };
}

function buildMessages() {
    const msgs = [];
    const { hours, mm } = alertCfg();
    if (selectedRain === hours) {
        const high = status.districts.filter(d => rainAlertOf(d)?.level === "high");
        const poss = status.districts.filter(d => rainAlertOf(d)?.level === "possible");
        if (high.length) msgs.push({ cls: "red", badge: "雨量警示",
            text: `${hours} 小時累積雨量超過 ${mm} mm：` +
                high.map(d => `${d.name}（${rainAlertOf(d).range} mm，${rainAlertOf(d).area_km2} km²）`).join("、") });
        if (poss.length) msgs.push({ cls: "orange", badge: "雨量可能",
            text: `${hours} 小時累積雨量可能超過 ${mm} mm（級距跨越門檻）：` +
                poss.map(d => `${d.name}（${rainAlertOf(d).range} mm）`).join("、") });
    }
    const roadAlerts = roadSensors.filter(isRoadAlert);
    if (roadAlerts.length) msgs.push({ cls: "red", badge: "路面淹水",
        text: `路面淹水感測器高度超過 ${roadThreshold()}：` +
            roadAlerts.map(s => `${s.name}（${s.district ?? "-"}，${s.height}）`).join("、") });
    if (roadData && roadData.enabled === false) msgs.push({ cls: "", badge: "感測器", text: `路面淹水感測器資料未取得：${roadData.reason ?? "未知原因"}` });

    const info = hourInfo[String(selectedFlood)];
    const flooded = status.districts.filter(d => isFlooded(d));
    if (info && !info.available) {
        msgs.push({ cls: "", badge: "淹水", text: `${floodLabel(selectedFlood)}：目前無可用的淹水範圍資料，並不代表沒有淹水。` });
    } else if (flooded.length) {
        const fc = selectedFlood !== 0;
        msgs.push({ cls: fc ? "orange" : "red", badge: fc ? "淹水預測" : "淹水",
            text: `${fc ? `預測 +${selectedFlood} 小時` : "偵測到"}淹水範圍：` +
                flooded.map(d => `${d.name} ${floodOf(d).area_km2} km²`).join("、") +
                `（依水利署淹水範圍圖自動判讀${fc ? "，為模型預測" : ""}，僅供參考）` });
    }
    const rinfo = status.rainfall_hours?.[String(selectedRain)];
    if (rinfo && !rinfo.available) msgs.push({ cls: "", badge: "提醒", text: `${selectedRain} 小時累積雨量目前無資料，請改選其他延時。` });
    else if (dataState().key === "stale") msgs.push({ cls: "", badge: "提醒", text: `資料已超過 ${STALE_HOURS} 小時未更新，請勿作為即時判斷依據。` });
    if (stationData && stationData.enabled === false) msgs.push({ cls: "", badge: "測站", text: `氣象署測站資料未啟用：${stationData.reason ?? "未知原因"}` });
    return msgs;
}

function renderAlerts() {
    const box = $("alerts");
    box.innerHTML = "";
    buildMessages().forEach(m => {
        const row = document.createElement("div");
        row.className = `alert ${m.cls}`.trim();
        const icon = m.cls === "red" ? "⚠" : m.cls === "orange" ? "▲" : "ℹ";
        const b = document.createElement("span"); b.className = "alert-badge"; b.textContent = `${icon} ${m.badge}`;
        const t = document.createElement("span"); t.className = "alert-text"; t.textContent = m.text;
        row.append(b, t);
        box.appendChild(row);
    });
}

function renderWarnings() {
    const items = [];
    const { hours, mm } = alertCfg();
    status.districts.forEach(d => {
        const a = rainAlertOf(d);
        if (a) items.push({ level: a.level === "high" ? "danger" : "warn",
            title: `${d.name} ${hours} 小時網格雨量${a.level === "high" ? "超過" : "可能超過"} ${mm} mm`,
            desc: `級距 ${a.range} mm，${a.cells} 格 / ${a.area_km2} km²` });
        if (isFlooded(d)) items.push({ level: selectedFlood === 0 ? "danger" : "warn",
            title: `${d.name} ${selectedFlood === 0 ? "偵測到淹水範圍" : `預測 +${selectedFlood}h 淹水`}`,
            desc: `面積 ${floodOf(d).area_km2} km²` });
    });
    stations.forEach(s => {
        const v = r1(s);
        if (v === null) return;
        if (v >= STATION_THRESHOLDS.danger) items.push({ level: "danger", title: `${s.name}測站達強降雨門檻`, desc: `1 小時雨量 ${v.toFixed(1)} mm（面板自訂門檻，非官方）` });
        else if (v >= STATION_THRESHOLDS.warning) items.push({ level: "warn", title: `${s.name}測站雨勢偏強`, desc: `1 小時雨量 ${v.toFixed(1)} mm（面板自訂門檻，非官方）` });
    });
    roadSensors.filter(isRoadAlert).forEach(s => items.push({ level: "danger",
        title: `${s.name} 路面淹水感測器示警`,
        desc: `${s.district ?? "-"}｜高度 ${s.height}（門檻 ${roadThreshold()}）｜${twTime(s.data_time)}` }));
    items.sort((a, b) => (b.level === "danger") - (a.level === "danger"));
    $("warningList").innerHTML = items.length
        ? items.map(w => `
            <div class="warning ${w.level === "danger" ? "warning-danger" : ""}">
              <span class="warning-dot"></span>
              <div><div class="warning-title">${esc(w.title)}</div><div class="warning-desc">${esc(w.desc)}</div></div>
            </div>`).join("")
        : `<div style="padding:18px 10px;text-align:center;color:var(--ok);font-weight:700">目前無明顯雨量警戒</div>`;
}

function renderSystem() {
    const st = dataState();
    const rinfo = status.rainfall_hours?.[String(selectedRain)];
    $("sysStatus").innerHTML = [
        ["資料狀態", `<strong style="color:${st.color}">${esc(st.text)}</strong>`],
        ["最後更新", `<strong>${esc(twTime(status.updated_at))}</strong>`],
        ["雨量資料時間", `<strong>${esc(twTime(rinfo?.window_end))}</strong>`],
        ["測站觀測時間", `<strong>${esc(twTime(stationData?.latest_obs_time))}</strong>`],
        ["路面感測器時間", `<strong>${esc(twTime(roadData?.latest_data_time))}</strong>`]
    ].map(([k, v]) => `<div class="sys-row"><span>${k}</span>${v}</div>`).join("");
    $("liveDot").style.background = st.color;
    $("liveText").textContent = st.key === "ok" ? "LIVE" : st.key === "partial" ? "PARTIAL" : "STALE";
}

/* =====================================================
   行政區卡片
===================================================== */
function renderDistricts() {
    const { hours, mm } = alertCfg();
    const rows = [...status.districts].sort((a, b) =>
        (isFlooded(b) - isFlooded(a)) ||
        (rainAlertOf(b) ? 1 : 0) - (rainAlertOf(a) ? 1 : 0) ||
        ((rainOf(b)?.mm ?? -1) - (rainOf(a)?.mm ?? -1)));
    $("districtHint").textContent = `${selectedRain} 小時累積雨量 · ${rows.length} 區`;
    $("districtGrid").innerHTML = rows.map(d => {
        const r = rainOf(d), a = rainAlertOf(d), fl = isFlooded(d);
        const ra = roadSensors.filter(x => x.district === d.name && isRoadAlert(x)).length;
        const st = stations.filter(s => s.district === d.name);
        const heavy = (selectedRain === hours && (r?.mm ?? 0) >= mm) ||
                      (maxOf(st, r1) ?? 0) >= STATION_THRESHOLDS.danger;
        const width = Math.min(((r?.mm ?? 0) / 100) * 100, 100);
        const range = r?.range == null ? "-" : r.range;
        return `
        <div class="district-card ${heavy ? "rain-heavy" : ""} ${fl || ra ? "flooded" : ""} ${a ? "rain-alert" : ""}" data-name="${esc(d.name)}">
          <div class="district-top">
            <span class="district-name">${esc(d.name)}
              ${fl ? '<span class="badge">⚠淹水</span>' : ""}
              ${ra ? `<span class="badge">⚠路面${ra}處</span>` : ""}
              ${a ? `<span class="badge ${a.level === "high" ? "rain" : "maybe"}">${a.level === "high" ? "⚠" : "△"}&gt;${esc(mm)}</span>` : ""}
            </span>
            <span class="district-rain">${esc(range)}<small>mm/${selectedRain}h${r?.dry ? " 推論" : ""}</small></span>
          </div>
          <div class="district-meta"><span>測站最大 1H / 24H</span>
            <span>${st.length ? `${esc(mmText(maxOf(st, r1)))} / ${esc(mmText(maxOf(st, r24)))}` : "-"}</span></div>
          <div class="sub"><span>淹水（${esc(floodLabel(selectedFlood))}）</span><span>${esc(fmt(floodOf(d)?.area_km2, "km²"))}</span></div>
          <div class="meter"><i style="width:${width}%"></i></div>
        </div>`;
    }).join("");
    $("districtGrid").querySelectorAll(".district-card").forEach(el => el.addEventListener("click", () => {
        const lyr = districtByName[el.dataset.name];
        if (lyr) { map.fitBounds(lyr.getBounds(), { padding: [30, 30] }); lyr.openPopup(); }
    }));
}

/* =====================================================
   控制項
===================================================== */
function updateWindowText() {
    const r = status.rainfall_hours?.[String(selectedRain)];
    $("windowText").textContent = r?.available && r.window_start && r.window_end
        ? `雨量統計區間：${twTime(r.window_start)} ～ ${twTime(r.window_end)}`
        : "雨量統計區間：-";
}

function fillSelects() {
    const fs = $("floodHour"), rs = $("rainHours");
    const fv = String(selectedFlood), rv = String(selectedRain);
    fs.innerHTML = "";
    for (let h = 0; h <= 6; h++) {
        const info = hourInfo[String(h)];
        const o = document.createElement("option");
        o.value = String(h);
        o.textContent = floodLabel(h) + (info && !info.available ? "（無資料）" : "");
        fs.appendChild(o);
    }
    rs.innerHTML = "";
    for (let h = 1; h <= 24; h++) {
        const info = status.rainfall_hours?.[String(h)];
        const o = document.createElement("option");
        o.value = String(h);
        o.textContent = `${h} 小時` + (info && !info.available ? "（無資料）" : "");
        rs.appendChild(o);
    }
    fs.value = fv; rs.value = rv;
}

function setupSelects() {
    fillSelects();
    const fs = $("floodHour"), rs = $("rainHours");
    fs.disabled = false; rs.disabled = false;
    fs.addEventListener("change", () => { selectedFlood = Number(fs.value); renderAll(); });
    rs.addEventListener("change", () => { selectedRain = Number(rs.value); renderAll(); });
}

/* =====================================================
   自動更新：依「更新週期」重新讀取資料，資料有變動才重繪
===================================================== */
const REFRESH_KEY = "taoyuan-water-refresh";

function signature(st, sd, rd) {
    return [st?.updated_at, sd?.updated_at, rd?.updated_at].join("|");
}

function applyData(st, sd, rd) {
    status = st;
    statusMap = Object.fromEntries(st.districts.map(d => [d.name, d]));
    hourInfo = st.inundation_hours ?? {};
    stationData = sd;
    stations = sd?.enabled ? (sd.stations ?? []) : [];
    roadData = rd;
    roadSensors = rd?.enabled ? (rd.sensors ?? []) : [];
}

function scheduleNext() { nextAt = Date.now() + refreshMin * 60000; }

function updateRefreshInfo() {
    const left = Math.max(0, Math.round((nextAt - Date.now()) / 1000));
    const mm = String(Math.floor(left / 60)).padStart(2, "0"), ss = String(left % 60).padStart(2, "0");
    $("nextCheck").textContent = reloading ? "檢查中…" : `${mm}:${ss}`;
    $("refreshInfo").textContent = lastCheck
        ? `上次檢查 ${lastCheck.toLocaleTimeString("zh-TW", { timeZone: "Asia/Taipei", hour12: false })}　${lastResult}`
        : "";
}

async function refreshData() {
    if (reloading) return;
    reloading = true; updateRefreshInfo();
    try {
        const [st, sd, rd] = await Promise.all([
            loadJSON("data/district_status.json"),
            loadOptionalJSON("data/stations.json"),
            loadOptionalJSON("data/road_sensors.json")
        ]);
        lastCheck = new Date();
        const sig = signature(st, sd, rd);
        if (sig !== currentSig) {
            currentSig = sig;
            applyData(st, sd, rd);
            Object.keys(rainCache).forEach(k => delete rainCache[k]);    // 網格/淹水 GeoJSON 重新讀取
            Object.keys(floodCache).forEach(k => delete floodCache[k]);
            fillSelects();
            renderStationMarkers(); renderKPI(); renderRanking();
            renderStationList($("stationSearch").value.trim());
            await renderAll();
            lastResult = "資料已更新";
        } else {
            lastResult = "資料無變動";
        }
    } catch (e) {
        console.warn("refresh failed", e);
        lastCheck = new Date();
        lastResult = "讀取失敗，保留目前畫面";
    } finally {
        reloading = false; scheduleNext(); updateRefreshInfo();
    }
}

function setupRefresh() {
    try {
        const v = Number(localStorage.getItem(REFRESH_KEY));
        if (REFRESH_OPTIONS.includes(v)) refreshMin = v;
    } catch { /* ignore */ }
    const sel = $("refreshSel");
    sel.value = String(refreshMin);
    sel.addEventListener("change", () => {
        refreshMin = Number(sel.value);
        try { localStorage.setItem(REFRESH_KEY, String(refreshMin)); } catch { /* ignore */ }
        scheduleNext(); updateRefreshInfo();
    });
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && Date.now() >= nextAt) refreshData();
    });
    scheduleNext();
    setInterval(() => {
        if (document.visibilityState === "visible" && Date.now() >= nextAt) refreshData();
        updateRefreshInfo();
    }, 1000);
    updateRefreshInfo();
}

function startClock() {
    const fmtParts = new Intl.DateTimeFormat("zh-TW", {
        timeZone: "Asia/Taipei", hour12: false, year: "numeric", month: "2-digit",
        day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
    const tick = () => {
        const p = Object.fromEntries(fmtParts.formatToParts(new Date()).map(x => [x.type, x.value]));
        $("clock").innerHTML =
            `<span class="clock-date">${p.year}/${p.month}/${p.day} </span>` +
            `${p.hour}:${p.minute}:${p.second}<span class="clock-tz"> (臺灣)</span>`;
    };
    tick(); setInterval(tick, 1000);
}

function setupTheme() {
    const KEY = "taoyuan-water-theme";
    try {
        const saved = localStorage.getItem(KEY);
        if (saved) document.documentElement.setAttribute("data-theme", saved);
        else if (window.matchMedia?.("(prefers-color-scheme: dark)").matches)
            document.documentElement.setAttribute("data-theme", "dark");
    } catch { /* storage 不可用時略過 */ }
    $("themeToggle").addEventListener("click", () => {
        const html = document.documentElement;
        const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
        html.setAttribute("data-theme", next);
        try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
    });
}

/* =====================================================
   主流程
===================================================== */
function renderAll() {
    updateWindowText();
    districtLayer.setStyle(styleFor);
    renderFloodMarkers();
    renderRainAlertMarkers();
    renderRoad();
    renderAlerts();
    renderWarnings();
    renderSystem();
    renderDistricts();
    return Promise.all([renderRain(), renderFlood()]);
}

async function main() {
    startClock();
    setupTheme();
    $("stationSearch").addEventListener("input", e => renderStationList(e.target.value.trim()));
    try {
        const [boundary, st, sd, rd] = await Promise.all([
            loadJSON("data/taoyuan_districts.geojson"),
            loadJSON("data/district_status.json"),
            loadOptionalJSON("data/stations.json"),
            loadOptionalJSON("data/road_sensors.json")
        ]);
        applyData(st, sd, rd);
        currentSig = signature(st, sd, rd);
        selectedRain = st.default_rainfall_hours ?? 1;

        districtLayer = L.geoJSON(boundary, {
            style: styleFor,
            onEachFeature: (f, lyr) => {
                districtByName[districtName(f.properties)] = lyr;
                lyr.bindPopup(() => popupHtml(districtName(f.properties)));
            }
        }).addTo(map);
        map.fitBounds(districtLayer.getBounds(), { padding: [20, 20] });

        addLegend();
        setupSelects();
        renderStationMarkers();
        renderKPI();
        renderRanking();
        renderStationList();
        await renderAll();
        setupRefresh();
    } catch (error) {
        console.error(error);
        $("windowText").textContent = "資料載入失敗，請稍後再試";
        $("alerts").innerHTML = '<div class="alert red"><span class="alert-badge">錯誤</span><span class="alert-text">資料載入失敗，請稍後再試。</span></div>';
    }
}

main();
