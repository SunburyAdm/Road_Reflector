# 02 — Connectivity Layer

LoRaWAN network and outdoor gateway configuration.

## Structure

```
02-connectivity-layer/
├── lorawan/   LoRaWAN US915 plan, OTAA keys policy, payload decoders
└── gateway/   Outdoor gateway configuration
```

## Recommended Setup

```
- LoRaWAN US915 frequency plan
- Outdoor LoRaWAN gateway
- Secure device registration
- OTAA device activation
- MQTT integration with backend services
```

## Gateway Options

```
Option A: RAK7289V2 Outdoor LoRaWAN Gateway
Option B: Milesight UG67 Outdoor LoRaWAN Gateway
```

The gateway receives data from multiple smart reflectors and forwards the
payloads to the cloud platform.
