# ESP32-C3 Bench Prototype

Current sensor-validation prototype running on an ESP32-C3. Used to validate the
thermistor (pavement temperature) and LIS3DH accelerometer (vibration) before
moving to the production RAK4631 / nRF52840 hardware.

## Sketches

| Folder | Description |
|--------|-------------|
| `Road_Reflector/` | Main reflector sketch |
| `Road_Reflector_Temperature/` | Temperature-focused sketch |
| `thermistor_and_lis3dh_2/` | Thermistor + LIS3DH combined test (with serial debug reader) |

> Live serial plotting tooling lives in [`../../tools/`](../../tools/).
