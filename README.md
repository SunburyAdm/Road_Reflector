# Smart Road Reflectors — Road Condition Monitoring & Data API Platform

Alpha Prototype of a Smart Road Reflector system that collects road condition
data, detects vehicle-related vibration events, transmits sensor data over a
LoRaWAN network, and exposes processed information through a cloud-based API,
dashboard, and 3D visualization.

## Repository Structure

```
.
├── docs/                     Project proposal, architecture, API, phases, budget
│
├── 01-device-layer/          Smart Road Reflector node
│   ├── firmware/             Production LoRaWAN firmware (RAK4631 / nRF52840)
│   ├── hardware/             Hardware design, recommended stack, placement
│   └── prototype-esp32c3/    Current ESP32-C3 bench prototype (sensor validation)
│
├── 02-connectivity-layer/    LoRaWAN network + outdoor gateway
│   ├── lorawan/
│   └── gateway/
│
├── 03-cloud-platform/        Ingestion, processing, storage, analytics
│   ├── chirpstack/           LoRaWAN Network Server
│   ├── mqtt-broker/          Mosquitto MQTT
│   ├── backend-fastapi/      FastAPI services
│   └── databases/            PostgreSQL + InfluxDB/TimescaleDB
│
├── 04-api-layer/             REST API, streaming API, auth, documentation
│
├── 05-data-consumers/        Visualization & consumer-facing layers
│   ├── web-dashboard/
│   ├── 3d-visualization/     Three.js
│   └── grafana/
│
└── tools/                    Helper scripts (live serial plotter, etc.)
```

## Documentation Index

| Document | Description |
|----------|-------------|
| [docs/01-project-proposal.md](docs/01-project-proposal.md) | Full Alpha Prototype proposal |
| [docs/02-architecture.md](docs/02-architecture.md) | 5-layer system architecture |
| [docs/03-api-design.md](docs/03-api-design.md) | API groups, endpoints, payloads |
| [docs/04-development-phases.md](docs/04-development-phases.md) | Phases 1–7 and Alpha scope |
| [docs/05-budget.md](docs/05-budget.md) | Estimated prototype budget |

## Architecture Layers

```
1. Device Layer       → Smart Road Reflector nodes with embedded sensors
2. Connectivity Layer → LoRaWAN network and outdoor gateway
3. Cloud Platform     → Ingestion, processing, validation, storage, analytics
4. API Layer          → REST API, streaming API, authentication, docs
5. Data Consumers     → Dashboard, agencies, fleets, insurers, ADAS/OEM users
```

## Technology Stack

```
Device        : RAK4631 / nRF52840 + SX1262, ADXL362, SHT31, water/tilt/piezo, LiFePO₄ + solar
Connectivity  : LoRaWAN US915, RAK7289V2 / Milesight UG67 gateway
Network Server: ChirpStack
Messaging     : Mosquitto MQTT
Backend       : FastAPI
Databases     : PostgreSQL + InfluxDB / TimescaleDB
Dashboard     : Grafana + custom web dashboard
3D            : Three.js
Docs          : OpenAPI / Swagger
Security      : LoRaWAN OTAA, API keys, JWT, HTTPS
```
