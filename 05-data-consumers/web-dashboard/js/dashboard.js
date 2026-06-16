/**
 * Smart Road Reflector — Dashboard controller
 * -------------------------------------------
 * Hydrates panels from the REST snapshot, drives the Three.js scene, and applies
 * live WebSocket events from the FastAPI backend (fed by the Python simulator).
 */
import { SiteScene } from "../../3d-visualization/js/scene.js";

const SITE_ID = "SITE-EAST-LIBERTY";
const API = window.location.origin;
const WS_URL = `${API.replace(/^http/, "ws")}/v1/stream/events`;

const $ = (id) => document.getElementById(id);
const fmtTime = (ts) => new Date(ts).toLocaleTimeString();

let scene;
let segments = [];
const sensorState = new Map();
const activeAlerts = new Map();
let trafficWindowCount = 0;

// --------------------------------------------------------------------------- //
async function boot() {
  scene = new SiteScene($("scene"));
  try {
    const config = await fetch(`${API}/v1/sites/${SITE_ID}/config`).then((r) => r.json());
    segments = (config.road_segments || []).map((s) => s.segment_id);
    scene.build(config);
    renderSensorSkeleton(config.sensors || []);
    logApi("GET", "/v1/sites/.../config", "200");
  } catch (e) {
    logApi("GET", "/v1/sites/.../config", "ERR");
  }
  await hydrate();
  connectWs();
  setInterval(refreshRoadCondition, 5000);
  refreshRoadCondition();
}

async function hydrate() {
  try {
    const snap = await fetch(`${API}/v1/dashboard/snapshot`).then((r) => r.json());
    logApi("GET", "/v1/dashboard/snapshot", "200");
    (snap.devices || []).forEach((d) => {
      if (d.latest) applyTelemetry(d.latest, false);
    });
    (snap.vehicle_events || []).forEach((e) => addVehicleRow(e, false));
    (snap.active_alerts || []).forEach((a) => upsertAlert(a));
    updateSim(snap.simulation);
    updateKpis();
  } catch (e) {
    logApi("GET", "/v1/dashboard/snapshot", "ERR");
  }
}

// ------------------------------- WebSocket --------------------------------- //
function connectWs() {
  const ws = new WebSocket(WS_URL);
  ws.onopen = () => setPill($("wsPill"), $("wsText"), "live", "WebSocket live");
  ws.onclose = () => {
    setPill($("wsPill"), $("wsText"), "down", "WebSocket down");
    setTimeout(connectWs, 2000);
  };
  ws.onmessage = (msg) => handleEvent(JSON.parse(msg.data));
}

function handleEvent(evt) {
  const { kind, data } = evt;
  switch (kind) {
    case "telemetry":
      applyTelemetry(data, true);
      break;
    case "vehicle_event":
      applyVehicleEvent(data);
      break;
    case "alert":
      upsertAlert(data);
      break;
    case "simulation_status":
      updateSim(data);
      break;
  }
  pushFeed(kind, data);
  updateKpis();
}

// ------------------------------- Telemetry --------------------------------- //
function applyTelemetry(t, live) {
  sensorState.set(t.device_id, t);
  scene.setSensorState(t.device_id, t);
  updateSensorRow(t);
  if (live) logApi("POST", "/v1/ingest/telemetry", t.device_id);
}

function renderSensorSkeleton(sensors) {
  const list = $("sensorList");
  list.innerHTML = "";
  sensors.forEach((s) => {
    const li = document.createElement("li");
    li.id = `sensor-${s.device_id}`;
    li.innerHTML = `<span class="s-dot offline"></span>
      <span class="s-id">${s.device_id}</span>
      <span class="s-meta" data-role>${s.role}</span>`;
    list.appendChild(li);
  });
}

function stateOf(t) {
  if (String(t.device_status) === "offline") return "offline";
  if (t.surface_water || (t.accel_peak_g || 0) >= 1.2) return "critical";
  if ((t.battery_pct ?? 100) <= 20) return "warning";
  return "ok";
}

function updateSensorRow(t) {
  const li = $(`sensor-${t.device_id}`);
  if (!li) return;
  const st = stateOf(t);
  li.querySelector(".s-dot").className = `s-dot ${st}`;
  li.querySelector(".s-meta").innerHTML =
    `${t.pavement_temp_c?.toFixed(1) ?? "–"}°C · ${t.battery_pct?.toFixed(0) ?? "–"}%` +
    (t.surface_water ? " · 💧" : "");
}

// ----------------------------- Vehicle events ------------------------------ //
function applyVehicleEvent(e) {
  scene.spawnVehicle(e);
  (e.related_sensor_ids || []).forEach((sid) =>
    scene.pulseSensor(sid, e.event_type === "abnormal_vibration_event" ? 1.6 : 1)
  );
  addVehicleRow(e, true);
  trafficWindowCount++;
  if (e.event_type === "abnormal_vibration_event")
    e.related_sensor_ids?.forEach((sid) => scene.addAlertMarker(sid, 0xff4d4f));
  logApi("POST", "/v1/ingest/vehicle-event", e.event_type);
}

function addVehicleRow(e, prepend) {
  const tbody = $("vehicleTable");
  const tr = document.createElement("tr");
  tr.innerHTML = `<td>${fmtTime(e.timestamp)}</td>
    <td>${e.event_type.replace(/_/g, " ")}</td>
    <td>${e.vehicle_class || "–"}</td>
    <td>${e.estimated_speed_kmh?.toFixed(0) ?? "–"}</td>
    <td>${e.segment_id || "–"}</td>`;
  if (prepend) tbody.prepend(tr);
  else tbody.appendChild(tr);
  while (tbody.rows.length > 40) tbody.deleteRow(-1);
}

// -------------------------------- Alerts ----------------------------------- //
function upsertAlert(a) {
  if (a.status !== "active") activeAlerts.delete(a.alert_id);
  else activeAlerts.set(a.alert_id, a);
  renderAlerts();
  if (a.status === "active" && a.device_id) {
    const color = a.severity === "critical" ? 0xff4d4f : 0xffb020;
    scene.addAlertMarker(a.device_id, color);
  }
}

function renderAlerts() {
  const list = $("alertList");
  const items = [...activeAlerts.values()].slice(-30).reverse();
  list.innerHTML = "";
  items.forEach((a) => {
    const li = document.createElement("li");
    li.className = a.severity;
    li.innerHTML = `<div class="a-type">${a.type.replace(/_/g, " ")}</div>
      <div class="a-msg">${a.message || ""}</div>`;
    list.appendChild(li);
  });
  $("alertBadge").textContent = activeAlerts.size;
}

// --------------------------- Road condition -------------------------------- //
async function refreshRoadCondition() {
  const grid = $("roadCondition");
  const cards = await Promise.all(
    segments.map((sid) =>
      fetch(`${API}/v1/road-segments/${sid}/condition`)
        .then((r) => r.json())
        .catch(() => null)
    )
  );
  grid.innerHTML = "";
  cards.filter(Boolean).forEach((c) => {
    const div = document.createElement("div");
    div.className = `road-card ${c.condition}`;
    div.innerHTML = `<div class="rc-seg">${c.segment_id}</div>
      <div class="rc-state">${c.condition.replace(/_/g, " ")}</div>
      <div class="rc-seg">${c.avg_pavement_temp_c ?? "–"}°C ${c.surface_water ? "· 💧" : ""}</div>`;
    grid.appendChild(div);
  });
}

// --------------------------------- KPIs ------------------------------------ //
function updateKpis() {
  const temps = [...sensorState.values()]
    .map((t) => t.pavement_temp_c)
    .filter((v) => v != null);
  const online = [...sensorState.values()].filter(
    (t) => String(t.device_status) !== "offline"
  ).length;
  $("kpiSensors").textContent = `${online}/${sensorState.size || "–"}`;
  $("kpiAlerts").textContent = activeAlerts.size;
  $("kpiTraffic").textContent = trafficWindowCount;
  $("kpiTemp").textContent = temps.length
    ? (temps.reduce((a, b) => a + b, 0) / temps.length).toFixed(1)
    : "–";
}
setInterval(() => {
  trafficWindowCount = Math.max(0, trafficWindowCount - 1); // slow decay for the 2-min feel
}, 6000);

// -------------------------- Sim status / feed / log ------------------------ //
function updateSim(sim) {
  if (!sim) return;
  const cls = sim.state === "live" ? "live" : sim.state === "stale" ? "stale" : "down";
  setPill($("simPill"), $("simText"), cls, `Feeder ${sim.state}`);
}

function setPill(pill, textEl, cls, text) {
  pill.className = `pill ${cls}`;
  textEl.textContent = text;
}

function pushFeed(kind, data) {
  const feed = $("feed");
  const li = document.createElement("li");
  const label =
    data.device_id || data.event_type || data.type || data.state || "";
  li.innerHTML = `<span class="t">${fmtTime(data.timestamp || Date.now())}</span>
    <span class="tag ${kind}">${kind.replace("_", " ")}</span>
    <span>${label}</span>`;
  feed.prepend(li);
  while (feed.children.length > 60) feed.lastChild.remove();
}

function logApi(method, path, status) {
  const log = $("apiLog");
  const li = document.createElement("li");
  li.innerHTML = `<span class="method">${method}</span> ${path} <span class="t">→ ${status}</span>`;
  log.prepend(li);
  while (log.children.length > 50) log.lastChild.remove();
}

$("clearFeed").addEventListener("click", () => ($("feed").innerHTML = ""));

boot();
