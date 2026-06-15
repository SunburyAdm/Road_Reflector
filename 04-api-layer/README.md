# 04 — API Layer

REST API, streaming API, authentication, and documentation.

The implementation lives in [`../03-cloud-platform/backend-fastapi/`](../03-cloud-platform/backend-fastapi/).
This folder holds the API contract, specs, and gateway/auth configuration.

## Main API Groups

```
Device API
Telemetry API
Road Condition API
Vehicle Event API
Alert API
Streaming API
```

## Security

```
- API keys for external consumers
- JWT authentication for dashboard users
- Rate limiting
- Request logging
- HTTPS for all API traffic
```

> Full endpoint list and example payloads: [`../docs/03-api-design.md`](../docs/03-api-design.md).
