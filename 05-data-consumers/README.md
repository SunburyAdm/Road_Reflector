# 05 — Data Consumers

Visualization and consumer-facing layers.

## Structure

```
05-data-consumers/
├── web-dashboard/      Custom technical web dashboard
├── 3d-visualization/   Three.js real-time 3D road visualization
└── grafana/            Grafana dashboards
```

## Technical Dashboard

```
- Sensor location map
- Device online/offline status
- Battery level / solar charging status
- Pavement temperature / humidity / surface water
- Vibration levels / tilt or movement alerts
- Communication quality
- Historical trends
- Active alerts
- Exportable reports
```

## 3D Road Visualization (Three.js)

```
- Road segment model
- Smart reflectors installed on the road
- Real-time vehicle events
- Vehicle size approximation
- Vibration waves around sensors
- Road condition color indicators
- Live sensor values
- Alerts and event markers
```

Connected to the backend through WebSocket events (`WS /v1/stream/events`).

## Consumers

Government agencies, road maintenance companies, insurance companies, fleet and
logistics operators, universities and research labs, OEM / ADAS / autonomous
vehicle teams.
