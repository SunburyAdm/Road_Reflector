# 01 — Device Layer

Smart Road Reflector node: embedded electronics, firmware, and hardware design.

## Structure

```
01-device-layer/
├── firmware/            Production LoRaWAN firmware (RAK4631 / nRF52840 + SX1262)
├── hardware/            Hardware design, recommended stack, bring-up notes
└── prototype-esp32c3/   Current ESP32-C3 bench prototype (sensor validation)
```

## Core Hardware Target

```
MCU + LoRaWAN : RAK4631 / nRF52840 + SX1262
Accelerometer : ADXL362 (low-power IMU)
Temp/Humidity : SHT31 + pavement temperature sensor
Other sensors : surface water sensor, tilt detection, optional piezo impact
Power         : LiFePO₄ battery + solar panel + solar charging + regulator
```

## Measured Signals

Vibration / acceleration, pavement temperature, internal humidity, surface
water presence, tilt / displacement, impact intensity, battery voltage, solar
charging voltage, communication signal quality.
