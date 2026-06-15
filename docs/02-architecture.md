# System Architecture

The platform is divided into five main layers. Each layer maps to a top-level
folder in this repository.

| Layer | Folder | Responsibility |
|-------|--------|----------------|
| 1. Device Layer | [`01-device-layer/`](../01-device-layer/) | Smart Road Reflector nodes with embedded sensors |
| 2. Connectivity Layer | [`02-connectivity-layer/`](../02-connectivity-layer/) | LoRaWAN network and outdoor gateway |
| 3. Cloud Platform | [`03-cloud-platform/`](../03-cloud-platform/) | Ingestion, processing, validation, storage, analytics |
| 4. API Layer | [`04-api-layer/`](../04-api-layer/) | REST API, streaming API, authentication, documentation |
| 5. Data Consumers | [`05-data-consumers/`](../05-data-consumers/) | Dashboard, agencies, fleets, insurers, ADAS/OEM users |

---

## 4. Device Layer — Smart Road Reflector Node

### Core Hardware

```
MCU + LoRaWAN:
- RAK4631 / nRF52840 + SX1262 LoRa module

Main sensors:
- Low-power accelerometer / IMU
- Pavement temperature sensor
- Internal temperature and humidity sensor
- Surface water detection sensor
- Tilt / movement detection
- Optional piezo impact sensor

Power system:
- LiFePO₄ rechargeable battery
- Solar panel
- Solar charging circuit
- High-efficiency power regulator

Mechanical:
- Low-profile reflector enclosure
- Weather-resistant sealing
- Road-safe housing
- Replaceable or serviceable electronics module
```

### Sensor Capabilities

```
- Vibration / acceleration
- Pavement temperature
- Internal humidity
- Surface water presence
- Tilt or displacement
- Impact intensity
- Battery voltage
- Solar charging voltage
- Communication signal quality
```

---

## 5. Connectivity Layer

```
- LoRaWAN US915 frequency plan
- Outdoor LoRaWAN gateway
- Secure device registration
- OTAA device activation
- MQTT integration with backend services
```

### Gateway Options

```
Option A: RAK7289V2 Outdoor LoRaWAN Gateway
Option B: Milesight UG67 Outdoor LoRaWAN Gateway
```

---

## 6. Cloud Platform — Recommended Software Stack

```
LoRaWAN Network Server : ChirpStack
Message Broker         : Mosquitto MQTT
Backend API            : FastAPI
Relational Database    : PostgreSQL
Time-Series Database   : InfluxDB or TimescaleDB
Dashboard              : Grafana + custom web dashboard
3D Visualization       : Three.js
Documentation          : OpenAPI / Swagger
```

---

## 10. Vehicle Detection Method

Multiple reflectors installed along a lane estimate vehicle movement by
comparing vibration arrival times.

```
Traffic Direction →

S1 -------- 4 m -------- S2 -------- 4 m -------- S3
```

Estimated outputs: direction, approximate speed, event duration, approximate
vehicle length, number of vibration peaks, possible axle count, vehicle size class.

```
speed          = distance_between_sensors / time_difference
vehicle_length = estimated_speed × event_duration
```

---

## 12. Security and Reliability

```
Device Security        : Unique device ID, unique LoRaWAN keys, OTAA, signed firmware (future)
Communication Security : LoRaWAN encryption, HTTPS for API, MQTT authentication
API Security           : API keys, JWT for dashboard, rate limiting, request logging
Platform Reliability   : DB backups, gateway monitoring, device health, cloud logs, offline alerts
```
