# API Design

## 7. API Layer

The API layer exposes sensor values, road condition data, vehicle events,
alerts, and device status.

### Main API Groups

```
Device API
Telemetry API
Road Condition API
Vehicle Event API
Alert API
Streaming API
```

### Example API Endpoints

```
GET  /v1/devices
GET  /v1/devices/{device_id}
GET  /v1/devices/{device_id}/latest
GET  /v1/devices/{device_id}/readings

GET  /v1/segments
GET  /v1/segments/{segment_id}/condition
GET  /v1/segments/{segment_id}/traffic-summary

GET  /v1/vehicle-events
GET  /v1/vehicle-events/{event_id}

GET  /v1/alerts
GET  /v1/alerts/active

POST /v1/ingest/telemetry
POST /v1/ingest/vehicle-event

WS   /v1/stream/events
```

---

## 8. Example Sensor Telemetry Payload

```json
{
  "device_id": "SRR-OH-001",
  "timestamp": "2026-06-12T19:20:10.000Z",
  "battery_v": 3.42,
  "battery_pct": 78,
  "solar_v": 5.18,
  "pavement_temp_c": 31.4,
  "internal_temp_c": 29.8,
  "humidity_pct": 61.2,
  "surface_water": false,
  "tilt_deg": 1.3,
  "accel_rms": 0.084,
  "accel_peak_g": 0.36,
  "vibration_energy": 12.7,
  "rssi": -105,
  "snr": 7.4
}
```

---

## 9. Example Vehicle Event Payload

```json
{
  "vehicle_event_id": "VEH-000482",
  "segment_id": "OH-TEST-001",
  "lane": 1,
  "timestamp": "2026-06-12T19:20:11.240Z",
  "sensor_ids": [
    "SRR-OH-001",
    "SRR-OH-002",
    "SRR-OH-003"
  ],
  "estimated_speed_kmh": 72.4,
  "estimated_length_m": 4.9,
  "estimated_axles": 2,
  "vehicle_class": "large_vehicle",
  "confidence": 0.84
}
```

### Initial Vehicle Classes

```
- small_vehicle
- medium_vehicle
- large_vehicle
- heavy_vehicle
- unknown
```
