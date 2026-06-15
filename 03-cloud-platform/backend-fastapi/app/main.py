"""
Smart Road Reflector — Alpha Demonstration Platform
FastAPI backend: ingestion, REST API, WebSocket streaming, road intelligence.

Run:
    uvicorn app.main:app --reload --port 8000
    (from the 03-cloud-platform/backend-fastapi directory)

Docs:  http://localhost:8000/docs
Dash:  http://localhost:8000/  (serves the static dashboard)
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, intelligence
from .schemas import (
    Alert,
    AlertIn,
    IngestResponse,
    StreamEvent,
    Telemetry,
    TelemetryIn,
    VehicleEvent,
    VehicleEventIn,
)
from .store import store
from .ws_manager import manager

app = FastAPI(
    title="Smart Road Reflector — Alpha Demonstration Platform",
    description=(
        "Office-campus Smart Road Reflector demo backend. Ingests simulated "
        "telemetry, vehicle events, and alerts; derives road-condition "
        "intelligence; and broadcasts live events over WebSocket. Designed so the "
        "Python simulation feeder can later be replaced by real LoRaWAN / "
        "ChirpStack / MQTT data without API changes."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
async def _broadcast(kind: str, payload) -> None:
    await manager.broadcast(
        StreamEvent(kind=kind, data=payload.model_dump(mode="json"))
    )


async def _emit_alerts(alerts: List[Alert]) -> List[str]:
    ids: List[str] = []
    for a in alerts:
        store.add_alert(a)
        await _broadcast("alert", a)
        ids.append(a.alert_id)
    return ids


# --------------------------------------------------------------------------- #
# Ingestion endpoints (consumed by the Python simulation feeder)              #
# --------------------------------------------------------------------------- #
@app.post("/v1/ingest/telemetry", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_telemetry(payload: TelemetryIn) -> IngestResponse:
    record = Telemetry(**payload.model_dump(), is_simulated=True)
    store.add_telemetry(record)
    await _broadcast("telemetry", record)
    derived = await _emit_alerts(intelligence.evaluate_telemetry(record))
    return IngestResponse(
        id=record.device_id, kind="telemetry", derived_alerts=derived
    )


@app.post(
    "/v1/ingest/vehicle-event", response_model=IngestResponse, tags=["Ingestion"]
)
async def ingest_vehicle_event(payload: VehicleEventIn) -> IngestResponse:
    record = VehicleEvent(**payload.model_dump(), is_simulated=True)
    store.add_vehicle_event(record)
    await _broadcast("vehicle_event", record)
    derived = await _emit_alerts(intelligence.evaluate_vehicle_event(record))
    derived += await _emit_alerts(intelligence.evaluate_traffic(store))
    return IngestResponse(
        id=record.vehicle_event_id, kind="vehicle_event", derived_alerts=derived
    )


@app.post("/v1/ingest/alert", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_alert(payload: AlertIn) -> IngestResponse:
    record = Alert(**payload.model_dump(), is_simulated=True)
    store.add_alert(record)
    await _broadcast("alert", record)
    return IngestResponse(id=record.alert_id, kind="alert")


# --------------------------------------------------------------------------- #
# Site / device / segment / parking REST API                                  #
# --------------------------------------------------------------------------- #
@app.get("/v1/sites/{site_id}/overview", tags=["Sites"])
def site_overview(site_id: str):
    cfg = config.load_site_config()
    if cfg["site"]["site_id"] != site_id:
        raise HTTPException(404, "Unknown site_id")

    latest = store.all_latest()
    online = sum(
        1 for t in latest if str(t.device_status) not in ("offline",)
    )
    active = store.active_alerts(limit=500)
    recent_vehicles = store.recent_vehicle_events(config.TRAFFIC_WINDOW_S)
    return {
        "site": cfg["site"],
        "building": cfg["building"],
        "counts": {
            "sensors_total": len(cfg["sensors"]),
            "sensors_reporting": len(latest),
            "sensors_online": online,
            "active_alerts": len(active),
            "vehicle_events_window": len(recent_vehicles),
        },
        "simulation": store.simulation_status(),
    }


@app.get("/v1/sites/{site_id}/config", tags=["Sites"])
def site_config(site_id: str):
    cfg = config.load_site_config()
    if cfg["site"]["site_id"] != site_id:
        raise HTTPException(404, "Unknown site_id")
    return cfg


@app.get("/v1/sites/{site_id}/devices", tags=["Devices"])
def site_devices(site_id: str):
    cfg = config.load_site_config()
    if cfg["site"]["site_id"] != site_id:
        raise HTTPException(404, "Unknown site_id")
    out = []
    for s in cfg["sensors"]:
        latest = store.latest(s["device_id"])
        out.append(
            {
                **s,
                "latest": latest.model_dump(mode="json") if latest else None,
            }
        )
    return {"site_id": site_id, "devices": out}


@app.get("/v1/devices/{device_id}/latest", response_model=Telemetry, tags=["Devices"])
def device_latest(device_id: str):
    latest = store.latest(device_id)
    if not latest:
        raise HTTPException(404, "No telemetry for this device yet")
    return latest


@app.get(
    "/v1/devices/{device_id}/readings",
    response_model=List[Telemetry],
    tags=["Devices"],
)
def device_readings(device_id: str, limit: int = Query(200, ge=1, le=2000)):
    return store.readings(device_id, limit=limit)


@app.get("/v1/road-segments/{segment_id}/condition", tags=["Road Condition"])
def segment_condition(segment_id: str):
    cfg = config.load_site_config()
    sensors = [s for s in cfg["sensors"] if s.get("segment_id") == segment_id]
    latest = [
        store.latest(s["device_id"])
        for s in sensors
        if store.latest(s["device_id"])
    ]
    temps = [t.pavement_temp_c for t in latest if t.pavement_temp_c is not None]
    water = any(bool(t.surface_water) for t in latest)
    seg_alerts = [
        a for a in store.active_alerts(500) if a.segment_id == segment_id
    ]
    condition = "normal"
    if any(a.type == "ice_risk" for a in seg_alerts):
        condition = "ice_risk"
    elif water:
        condition = "surface_water"
    elif any(a.type in ("possible_pothole", "high_vibration") for a in seg_alerts):
        condition = "pavement_attention"
    return {
        "segment_id": segment_id,
        "condition": condition,
        "avg_pavement_temp_c": round(sum(temps) / len(temps), 2) if temps else None,
        "surface_water": water,
        "active_alerts": [a.model_dump(mode="json") for a in seg_alerts],
        "sensor_count": len(sensors),
        "reporting": len(latest),
    }


@app.get("/v1/parking/{parking_zone_id}/summary", tags=["Parking"])
def parking_summary(parking_zone_id: str):
    cfg = config.load_site_config()
    zone = next(
        (
            z
            for z in cfg.get("parking_zones", [])
            if z["parking_zone_id"] == parking_zone_id
        ),
        None,
    )
    if not zone:
        raise HTTPException(404, "Unknown parking_zone_id")

    events = store.recent_vehicle_events(config.TRAFFIC_WINDOW_S)
    parked = sum(1 for e in events if e.event_type == "vehicle_parking")
    left = sum(1 for e in events if e.event_type == "vehicle_leaving_parking")
    turning = sum(
        1 for e in events if e.event_type == "vehicle_turning_into_parking"
    )
    net = parked - left
    occupancy_pct = (
        round(min(max(net, 0) / zone["capacity"] * 100, 100), 1)
        if zone.get("capacity")
        else None
    )
    return {
        "parking_zone": zone,
        "window_s": config.TRAFFIC_WINDOW_S,
        "parked_events": parked,
        "left_events": left,
        "turning_in_events": turning,
        "net_inflow": net,
        "estimated_occupancy_pct": occupancy_pct,
    }


@app.get(
    "/v1/vehicle-events", response_model=List[VehicleEvent], tags=["Vehicle Events"]
)
def list_vehicle_events(
    segment_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    return store.vehicle_events(
        segment_id=segment_id, event_type=event_type, limit=limit
    )


@app.get("/v1/alerts/active", response_model=List[Alert], tags=["Alerts"])
def active_alerts(limit: int = Query(100, ge=1, le=1000)):
    return store.active_alerts(limit=limit)


@app.post("/v1/alerts/{alert_id}/acknowledge", response_model=Alert, tags=["Alerts"])
async def acknowledge_alert(alert_id: str):
    a = store.acknowledge_alert(alert_id)
    if not a:
        raise HTTPException(404, "Unknown alert_id")
    await _broadcast("alert", a)
    return a


@app.get("/v1/simulation/status", tags=["Simulation"])
def simulation_status():
    return store.simulation_status()


@app.get("/v1/dashboard/snapshot", tags=["Dashboard"])
def dashboard_snapshot():
    """One-shot payload to hydrate the dashboard on load."""
    cfg = config.load_site_config()
    return {
        "site": cfg["site"],
        "devices": [
            {
                **s,
                "latest": (
                    store.latest(s["device_id"]).model_dump(mode="json")
                    if store.latest(s["device_id"])
                    else None
                ),
            }
            for s in cfg["sensors"]
        ],
        "vehicle_events": [
            e.model_dump(mode="json") for e in store.vehicle_events(limit=40)
        ],
        "active_alerts": [
            a.model_dump(mode="json") for a in store.active_alerts(limit=50)
        ],
        "simulation": store.simulation_status(),
    }


@app.get("/v1/health", tags=["System"])
def health():
    return {"status": "ok", "ws_clients": manager.count}


# --------------------------------------------------------------------------- #
# WebSocket stream                                                             #
# --------------------------------------------------------------------------- #
@app.websocket("/v1/stream/events")
async def stream_events(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Greet with current simulation status so the UI can render immediately.
        await ws.send_json(
            StreamEvent(
                kind="simulation_status", data=store.simulation_status()
            ).model_dump(mode="json")
        )
        while True:
            # Keep the socket open; ignore inbound (client is read-only).
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)


# --------------------------------------------------------------------------- #
# Static dashboard + 3D assets (served from 05-data-consumers)                #
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parents[3]
_CONSUMERS = _ROOT / "05-data-consumers"
if _CONSUMERS.exists():
    app.mount(
        "/app",
        StaticFiles(directory=str(_CONSUMERS), html=True),
        name="data-consumers",
    )


@app.get("/", include_in_schema=False)
def root():
    if _CONSUMERS.exists():
        return RedirectResponse(url="/app/web-dashboard/index.html")
    return {"message": "Backend running. Dashboard assets not found.", "docs": "/docs"}
