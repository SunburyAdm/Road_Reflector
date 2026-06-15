"""
Smart Road Reflector — Simulation Feeder
=========================================

Temporary source-of-truth that generates synthetic Smart Road Reflector telemetry,
vehicle events, and alerts for the office-campus Alpha demo, and POSTs them to the
FastAPI backend ingestion endpoints:

    POST /v1/ingest/telemetry
    POST /v1/ingest/vehicle-event
    POST /v1/ingest/alert

The backend stores the data, derives road-condition intelligence, and broadcasts
everything over WS /v1/stream/events to the dashboard and 3D view.

This feeder is intentionally decoupled: it pulls the site geometry (sensors, paths,
parking zones) from the backend's /v1/sites/{id}/config endpoint, so it always matches
the deployed site model. When real LoRaWAN / ChirpStack / MQTT data is available, this
script is simply switched off — the backend and dashboard stay the same.

Usage:
    python simulation_feeder.py
    python simulation_feeder.py --backend http://localhost:8000 --vehicle-rate 0.25
    python simulation_feeder.py --duration 120 --telemetry-interval 5

Requires: requests  (pip install requests)
"""
from __future__ import annotations

import argparse
import math
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

SITE_ID = "SITE-EAST-LIBERTY"
VEHICLE_CLASSES = [
    ("small_vehicle", 4.3, 2, 0.30),
    ("medium_vehicle", 4.9, 2, 0.45),
    ("large_vehicle", 5.6, 2, 0.60),
    ("delivery_van", 6.2, 2, 0.75),
    ("maintenance_truck", 8.5, 3, 1.05),
]
SENSOR_TRIGGER_RADIUS_M = 3.5


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Geometry helpers                                                            #
# --------------------------------------------------------------------------- #
def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def resample_path(waypoints: List[List[float]], step_m: float = 1.0
                  ) -> List[Tuple[float, float]]:
    """Convert polyline waypoints into evenly spaced points for smooth motion."""
    pts: List[Tuple[float, float]] = []
    for i in range(len(waypoints) - 1):
        a = (waypoints[i][0], waypoints[i][1])
        b = (waypoints[i + 1][0], waypoints[i + 1][1])
        seg = dist(a, b)
        n = max(1, int(seg / step_m))
        for k in range(n):
            t = k / n
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    pts.append((waypoints[-1][0], waypoints[-1][1]))
    return pts


# --------------------------------------------------------------------------- #
# Simulated vehicle                                                           #
# --------------------------------------------------------------------------- #
class Vehicle:
    _seq = 0

    def __init__(self, path: dict, sensors: List[dict], speed_kmh: float):
        Vehicle._seq += 1
        self.id = f"VEH-{Vehicle._seq:06d}"
        self.path_id = path["path_id"]
        self.path = path
        self.points = resample_path(path["waypoints_m"], step_m=1.0)
        self.idx = 0
        self.speed_kmh = speed_kmh
        self.speed_mps = speed_kmh / 3.6
        self.vclass, self.length_m, self.axles, self.veh_vib = random.choice(
            VEHICLE_CLASSES
        )
        self.sensors = sensors
        self.triggered: set[str] = set()
        self.done = False
        self.start_emitted = False

    @property
    def pos(self) -> Tuple[float, float]:
        return self.points[min(self.idx, len(self.points) - 1)]

    @property
    def direction(self) -> str:
        if self.idx + 1 >= len(self.points):
            return "outbound"
        a, b = self.points[self.idx], self.points[self.idx + 1]
        return "inbound" if b[0] >= a[0] else "outbound"

    def advance(self, dt: float) -> None:
        """Move along the resampled path; ~1 m spacing => steps per second = speed_mps."""
        steps = self.speed_mps * dt
        self.idx += max(1, int(round(steps)))
        if self.idx >= len(self.points) - 1:
            self.idx = len(self.points) - 1
            self.done = True

    def nearby_sensor(self) -> Optional[dict]:
        p = self.pos
        for s in self.sensors:
            sp = (s["position_m"]["x"], s["position_m"]["y"])
            if s["device_id"] not in self.triggered and dist(p, sp) <= SENSOR_TRIGGER_RADIUS_M:
                return s
        return None


# --------------------------------------------------------------------------- #
# Feeder                                                                       #
# --------------------------------------------------------------------------- #
class Feeder:
    def __init__(self, args):
        self.backend = args.backend.rstrip("/")
        self.args = args
        self.session = requests.Session()
        self.config = self._load_config()
        self.sensors = self.config["sensors"]
        self.paths = self.config["vehicle_paths"]
        self.sensor_by_id = {s["device_id"]: s for s in self.sensors}
        # Per-sensor slowly drifting baseline state.
        self.state: Dict[str, dict] = {
            s["device_id"]: {
                "battery_pct": random.uniform(70, 100),
                "vib_boost": 0.0,
                "water": False,
            }
            for s in self.sensors
        }
        self.vehicles: List[Vehicle] = []
        self.last_telemetry = 0.0
        # One sensor permanently flagged as the cold/drainage low spot for demo.
        self.drainage_id = next(
            (s["device_id"] for s in self.sensors if s.get("role") == "surface_water"),
            self.sensors[0]["device_id"],
        )

    # ----------------------------- setup ------------------------------- #
    def _load_config(self) -> dict:
        url = f"{self.backend}/v1/sites/{SITE_ID}/config"
        for attempt in range(30):
            try:
                r = self.session.get(url, timeout=3)
                if r.ok:
                    print(f"[feeder] loaded site config from {url}")
                    return r.json()
            except requests.RequestException:
                pass
            print(f"[feeder] waiting for backend at {self.backend} ... ({attempt + 1})")
            time.sleep(2)
        raise SystemExit(
            f"[feeder] could not reach backend at {self.backend}. Start the API first."
        )

    # ----------------------------- POST -------------------------------- #
    def _post(self, path: str, payload: dict) -> None:
        try:
            self.session.post(f"{self.backend}{path}", json=payload, timeout=3)
        except requests.RequestException as exc:
            print(f"[feeder] POST {path} failed: {exc}")

    # --------------------------- telemetry ----------------------------- #
    def emit_telemetry(self) -> None:
        season_temp = 7.0  # base ambient (°C) — tweak for ice-risk demos
        for s in self.sensors:
            dev = s["device_id"]
            st = self.state[dev]
            st["battery_pct"] = max(8.0, st["battery_pct"] - random.uniform(0, 0.05))
            battery_v = 2.9 + (st["battery_pct"] / 100.0) * 0.55

            is_drainage = dev == self.drainage_id
            water = is_drainage and random.random() < 0.15
            st["water"] = water
            pavement = season_temp + random.uniform(-2.5, 6.0) - (3.0 if water else 0.0)

            vib_boost = st["vib_boost"]
            st["vib_boost"] = max(0.0, vib_boost * 0.5)  # decay
            accel_peak = round(0.05 + random.uniform(0, 0.08) + vib_boost, 3)
            accel_rms = round(0.02 + random.uniform(0, 0.03) + vib_boost * 0.3, 3)
            vib_energy = round(5 + random.uniform(0, 10) + vib_boost * 70, 1)

            status = "ok"
            if st["battery_pct"] <= 20:
                status = "low_battery"

            payload = {
                "site_id": SITE_ID,
                "device_id": dev,
                "segment_id": s.get("segment_id"),
                "timestamp": iso_now(),
                "device_status": status,
                "battery_v": round(battery_v, 3),
                "battery_pct": round(st["battery_pct"], 1),
                "solar_v": round(max(0.0, random.uniform(0, 6.2)), 2),
                "pavement_temp_c": round(pavement, 2),
                "internal_temp_c": round(pavement + random.uniform(0, 3), 2),
                "humidity_pct": round(random.uniform(45, 95), 1),
                "surface_water": water,
                "accel_rms": accel_rms,
                "accel_peak_g": accel_peak,
                "vibration_energy": vib_energy,
                "tilt_deg": round(random.uniform(0.2, 2.5), 2),
                "rssi": round(random.uniform(-115, -95), 1),
                "snr": round(random.uniform(4, 11), 1),
            }
            self._post("/v1/ingest/telemetry", payload)

    # ------------------------- vehicle events -------------------------- #
    def spawn_vehicle(self) -> None:
        path = random.choice(self.paths)
        lo, hi = self.config["site"]["assumptions"]["vehicle_speed_range_kmh"]
        speed = random.uniform(lo, hi)
        self.vehicles.append(Vehicle(path, self.sensors, speed))

    def _event_type_for(self, v: Vehicle, sensor: dict) -> str:
        role = sensor.get("role")
        if role == "vehicle_count":
            if "PARK" in v.path_id and "LEAVE" in v.path_id:
                return "vehicle_leaving_parking"
            return "vehicle_turning_into_parking"
        if not v.start_emitted:
            v.start_emitted = True
            return (
                "vehicle_leaving_parking"
                if "LEAVE" in v.path_id
                else "vehicle_entering_site"
            )
        return "vehicle_passing_driveway"

    def emit_vehicle_event(self, v: Vehicle, sensor: dict, event_type: str) -> None:
        abnormal = random.random() < 0.06
        accel_peak = round(v.veh_vib * random.uniform(0.8, 1.2) + (0.9 if abnormal else 0), 3)
        accel_rms = round(accel_peak * 0.4, 3)
        vib_energy = round(20 + v.veh_vib * 30 + (90 if abnormal else 0), 1)
        # Boost that sensor's next telemetry vibration so the wave animation fires.
        self.state[sensor["device_id"]]["vib_boost"] += v.veh_vib * 0.6 + (1.0 if abnormal else 0)

        payload = {
            "vehicle_event_id": f"{v.id}-{sensor['device_id']}",
            "site_id": SITE_ID,
            "segment_id": sensor.get("segment_id"),
            "path_id": v.path_id,
            "timestamp": iso_now(),
            "event_type": "abnormal_vibration_event" if abnormal else event_type,
            "related_sensor_ids": [sensor["device_id"]],
            "vehicle_class": v.vclass,
            "direction": v.direction,
            "estimated_speed_kmh": round(v.speed_kmh, 1),
            "estimated_length_m": v.length_m,
            "estimated_axles": v.axles,
            "accel_peak_g": accel_peak,
            "accel_rms": accel_rms,
            "vibration_energy": vib_energy,
            "confidence": round(random.uniform(0.7, 0.97), 2),
        }
        self._post("/v1/ingest/vehicle-event", payload)

    def emit_terminal_event(self, v: Vehicle) -> None:
        payload = {
            "vehicle_event_id": f"{v.id}-terminal",
            "site_id": SITE_ID,
            "segment_id": None,
            "path_id": v.path_id,
            "timestamp": iso_now(),
            "event_type": v.path.get("terminal_event", "vehicle_passing_driveway"),
            "related_sensor_ids": v.path.get("related_sensor_ids", []),
            "vehicle_class": v.vclass,
            "direction": v.direction,
            "estimated_speed_kmh": round(v.speed_kmh, 1),
            "estimated_length_m": v.length_m,
            "estimated_axles": v.axles,
            "confidence": round(random.uniform(0.7, 0.97), 2),
        }
        self._post("/v1/ingest/vehicle-event", payload)

    # ------------------------------ loop ------------------------------- #
    def run(self) -> None:
        print(
            f"[feeder] streaming to {self.backend} "
            f"({len(self.sensors)} sensors, {len(self.paths)} paths). Ctrl+C to stop."
        )
        dt = 0.1
        t0 = time.time()
        try:
            while True:
                now = time.time()
                if self.args.duration and (now - t0) >= self.args.duration:
                    break

                # Telemetry tick.
                if now - self.last_telemetry >= self.args.telemetry_interval:
                    self.emit_telemetry()
                    self.last_telemetry = now

                # Vehicle spawning (Poisson-ish).
                if random.random() < self.args.vehicle_rate * dt:
                    self.spawn_vehicle()

                # Advance vehicles + emit proximity events.
                for v in list(self.vehicles):
                    v.advance(dt)
                    sensor = v.nearby_sensor()
                    if sensor:
                        v.triggered.add(sensor["device_id"])
                        self.emit_vehicle_event(
                            v, sensor, self._event_type_for(v, sensor)
                        )
                    if v.done:
                        self.emit_terminal_event(v)
                        self.vehicles.remove(v)

                time.sleep(dt)
        except KeyboardInterrupt:
            print("\n[feeder] stopped.")


def parse_args():
    p = argparse.ArgumentParser(description="Smart Road Reflector simulation feeder")
    p.add_argument("--backend", default="http://localhost:8000")
    p.add_argument(
        "--telemetry-interval", type=float, default=5.0,
        help="Seconds between telemetry bursts (all sensors).",
    )
    p.add_argument(
        "--vehicle-rate", type=float, default=0.15,
        help="Average vehicles spawned per second.",
    )
    p.add_argument(
        "--duration", type=float, default=0,
        help="Run time in seconds (0 = run until Ctrl+C).",
    )
    return p.parse_args()


if __name__ == "__main__":
    Feeder(parse_args()).run()
