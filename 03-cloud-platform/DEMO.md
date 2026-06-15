# Alpha Demonstration Platform — Run Guide

End-to-end demo of the **Smart Road Reflector** system for the East Liberty office
campus, using the Python simulation feeder as the temporary data source.

```
┌────────────────────┐   HTTP POST    ┌──────────────────┐   WebSocket    ┌────────────────────┐
│ simulation_feeder  │ ─────────────▶ │  FastAPI backend │ ─────────────▶ │ Dashboard + 3D view │
│ (tools/)           │  /v1/ingest/*  │  (in-memory)     │ /v1/stream/... │ (05-data-consumers) │
└────────────────────┘                └──────────────────┘                └────────────────────┘
        ▲ temporary                          ▲ swap-point
        │ source of truth                    │ store.py → PostgreSQL + TimescaleDB
        └── later replaced by LoRaWAN / ChirpStack / MQTT (same /v1/ingest/* contract)
```

## Components

| Part | Location |
|------|----------|
| Site model (geometry, sensors, paths) | `03-cloud-platform/backend-fastapi/app/data/site_east_liberty.json` |
| FastAPI backend | `03-cloud-platform/backend-fastapi/` |
| Database schema (production target) | `03-cloud-platform/databases/schema.sql` |
| Simulation feeder | `tools/simulation_feeder.py` |
| 3D visualization (Three.js) | `05-data-consumers/3d-visualization/js/scene.js` |
| Web dashboard | `05-data-consumers/web-dashboard/` |

## Run locally (Windows PowerShell)

**1 — Start the backend** (serves API + dashboard):

```powershell
cd 03-cloud-platform/backend-fastapi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**2 — Open the dashboard** in a browser:

```
http://localhost:8000/
```

Swagger UI is at http://localhost:8000/docs.

**3 — Start the simulation feeder** (new terminal):

```powershell
cd tools
pip install requests
python simulation_feeder.py
```

Optional knobs:

```powershell
python simulation_feeder.py --vehicle-rate 0.3 --telemetry-interval 4
python simulation_feeder.py --duration 120          # auto-stop after 2 minutes
python simulation_feeder.py --backend http://localhost:8000
```

**4 — Watch the dashboard.** The feeder status pill turns *live*, sensor nodes light
up, vehicles animate along the driveway and into parking, vibration rings pulse as
vehicles pass reflectors, and alerts (surface water, ice risk, high vibration, low
battery, parking congestion) appear in real time.

## Smart reflector nodes (8)

| ID | Role | Where |
|----|------|-------|
| SRR-OFFICE-001/002/003 | speed & direction | along the main driveway (30 m spacing) |
| SRR-OFFICE-004 | vehicle count | parking entry lane |
| SRR-OFFICE-005 | vehicle count | parking exit lane |
| SRR-OFFICE-006 | surface water / ice risk | drainage-prone low area |
| SRR-OFFICE-007/008 | parking condition | north / south parking rows |

## Switching to real data later

1. Stop `simulation_feeder.py`.
2. Add a ChirpStack/MQTT consumer that decodes uplinks and POSTs to the **same**
   `/v1/ingest/*` endpoints (or writes via `app/store.py`).
3. Point `store.py` at PostgreSQL + TimescaleDB using `databases/schema.sql`.

No changes are required in the API surface, intelligence logic, dashboard, or 3D view.
Records simply carry `is_simulated: false`.
