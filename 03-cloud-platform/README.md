# 03 — Cloud Platform

Data ingestion, processing, validation, storage, and analytics.

## Structure

```
03-cloud-platform/
├── chirpstack/        LoRaWAN Network Server (ChirpStack)
├── mqtt-broker/       Mosquitto MQTT broker config
├── backend-fastapi/   FastAPI ingestion + processing services
└── databases/         PostgreSQL (relational) + InfluxDB/TimescaleDB (time-series)
```

## Recommended Software Stack

```
LoRaWAN Network Server : ChirpStack
Message Broker         : Mosquitto MQTT
Backend API            : FastAPI
Relational Database    : PostgreSQL
Time-Series Database   : InfluxDB or TimescaleDB
Documentation          : OpenAPI / Swagger
```

## Data Flow

```
Reflector node → LoRaWAN gateway → ChirpStack → MQTT → FastAPI ingestion
              → validation → PostgreSQL (metadata/events) + InfluxDB (telemetry)
              → REST / WebSocket API → dashboards & consumers
```
