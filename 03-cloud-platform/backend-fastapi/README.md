# Backend — FastAPI (Alpha Demonstration Platform)

Ingestion, validation, storage, road-condition intelligence, REST API, and a
WebSocket stream for the Smart Road Reflector office-campus demo (East Liberty).

It accepts payloads from the Python simulation feeder **without manual edits** and
is structured so real LoRaWAN / ChirpStack / MQTT data can replace the feeder later
with no API or dashboard changes.

## Layout

```
backend-fastapi/
├── app/
│   ├── main.py          FastAPI app: ingestion, REST, WebSocket, static dashboard
│   ├── schemas.py       Pydantic models (Telemetry, VehicleEvent, Alert, StreamEvent)
│   ├── store.py         In-memory store (the swap-point for PostgreSQL/Timescale)
│   ├── intelligence.py  Road-condition & traffic alert logic
│   ├── ws_manager.py    WebSocket broadcast manager
│   ├── config.py        Settings + site-config loader
│   └── data/
│       └── site_east_liberty.json   Site model: segments, parking, sensors, paths
└── requirements.txt
```

## Run

```powershell
cd 03-cloud-platform/backend-fastapi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API docs (Swagger): http://localhost:8000/docs
- Dashboard:          http://localhost:8000/  (redirects to the static dashboard)
- WebSocket:          ws://localhost:8000/v1/stream/events

The demo runs fully **in-memory** — no database required. For production, swap the
methods in `app/store.py` to read/write the schema in
[`../databases/schema.sql`](../databases/schema.sql).

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/ingest/telemetry` | Sensor telemetry (from feeder) |
| POST | `/v1/ingest/vehicle-event` | Vehicle / parking events |
| POST | `/v1/ingest/alert` | Externally raised alerts |
| GET  | `/v1/sites/{id}/overview` | Site KPIs + simulation status |
| GET  | `/v1/sites/{id}/config` | Full site model (used by feeder + 3D) |
| GET  | `/v1/sites/{id}/devices` | Devices with latest reading |
| GET  | `/v1/devices/{id}/latest` | Latest telemetry |
| GET  | `/v1/devices/{id}/readings` | Telemetry history |
| GET  | `/v1/road-segments/{id}/condition` | Per-segment road condition |
| GET  | `/v1/parking/{zone}/summary` | Parking traffic summary |
| GET  | `/v1/vehicle-events` | Recent vehicle events |
| GET  | `/v1/alerts/active` | Active alerts |
| GET  | `/v1/simulation/status` | Feeder health |
| GET  | `/v1/dashboard/snapshot` | One-shot dashboard hydration |
| WS   | `/v1/stream/events` | Live telemetry / events / alerts |

## Future real-data integration

Replace the feeder with a ChirpStack MQTT consumer that decodes uplinks and calls the
same `/v1/ingest/*` endpoints (or the `store` directly). `intelligence.py` and the
dashboard are data-source agnostic; only `is_simulated` changes to `false`.

See [`../../docs/03-api-design.md`](../../docs/03-api-design.md) for the API contract.
