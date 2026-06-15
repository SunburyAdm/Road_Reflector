# Backend — FastAPI

Backend services for data ingestion, validation, processing, vehicle-event
estimation, and API exposure.

## Responsibilities
- Ingest telemetry from MQTT / ChirpStack
- Validate and store telemetry (time-series DB) and metadata/events (PostgreSQL)
- Vehicle-event estimation (speed, direction, length, axles, class)
- Serve REST API and WebSocket streaming API
- Publish OpenAPI / Swagger documentation

See [`../../docs/03-api-design.md`](../../docs/03-api-design.md) for the API contract.
