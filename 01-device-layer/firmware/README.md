# Firmware

Production firmware for the Smart Road Reflector node.

Target platform: **RAK4631 / nRF52840 + SX1262** with LoRaWAN US915 (OTAA).

## Planned responsibilities (Phase 4 / Phase 5)
- Sensor sampling (accelerometer, temperature, humidity, water, tilt)
- Vibration event detection
- Battery and solar charging monitoring
- LoRaWAN OTAA activation and uplink scheduling
- Compact telemetry payload encoding

> The current sensor-validation code runs on an ESP32-C3 bench prototype.
> See [`../prototype-esp32c3/`](../prototype-esp32c3/).
