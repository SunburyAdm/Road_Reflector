"""
In-memory data store for the Alpha demo.

This is the single integration seam for persistence. For the demo it keeps recent
records in bounded deques (no external DB required). To go to production, replace the
read/write methods here with PostgreSQL (metadata/events) + TimescaleDB/InfluxDB
(telemetry) calls — the API layer and WebSocket layer do not need to change.
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

from . import config
from .schemas import Alert, Telemetry, VehicleEvent


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()

        self._telemetry: Deque[Telemetry] = deque(maxlen=config.TELEMETRY_BUFFER)
        self._telemetry_by_device: Dict[str, Deque[Telemetry]] = defaultdict(
            lambda: deque(maxlen=2000)
        )
        self._latest_by_device: Dict[str, Telemetry] = {}

        self._vehicle_events: Deque[VehicleEvent] = deque(
            maxlen=config.VEHICLE_EVENT_BUFFER
        )
        self._alerts: Deque[Alert] = deque(maxlen=config.ALERT_BUFFER)
        self._alerts_by_id: Dict[str, Alert] = {}

        # Simulation-source bookkeeping.
        self._sim_last_seen: Optional[datetime] = None
        self._sim_counts = {"telemetry": 0, "vehicle_event": 0, "alert": 0}

    # ----------------------------- writes ------------------------------ #
    def add_telemetry(self, t: Telemetry) -> None:
        with self._lock:
            self._telemetry.append(t)
            self._telemetry_by_device[t.device_id].append(t)
            self._latest_by_device[t.device_id] = t
            self._mark_sim("telemetry")

    def add_vehicle_event(self, e: VehicleEvent) -> None:
        with self._lock:
            self._vehicle_events.append(e)
            self._mark_sim("vehicle_event")

    def add_alert(self, a: Alert) -> None:
        with self._lock:
            self._alerts.append(a)
            self._alerts_by_id[a.alert_id] = a
            self._mark_sim("alert")

    def _mark_sim(self, kind: str) -> None:
        self._sim_last_seen = _utcnow()
        self._sim_counts[kind] = self._sim_counts.get(kind, 0) + 1

    # ----------------------------- reads ------------------------------- #
    def latest(self, device_id: str) -> Optional[Telemetry]:
        with self._lock:
            return self._latest_by_device.get(device_id)

    def all_latest(self) -> List[Telemetry]:
        with self._lock:
            return list(self._latest_by_device.values())

    def readings(
        self, device_id: str, limit: int = 200
    ) -> List[Telemetry]:
        with self._lock:
            return list(self._telemetry_by_device.get(device_id, []))[-limit:]

    def vehicle_events(
        self,
        segment_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[VehicleEvent]:
        with self._lock:
            items = list(self._vehicle_events)
        if segment_id:
            items = [e for e in items if e.segment_id == segment_id]
        if event_type:
            items = [e for e in items if e.event_type == event_type]
        return items[-limit:]

    def alerts(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Alert]:
        with self._lock:
            items = list(self._alerts)
        if status:
            items = [a for a in items if a.status == status]
        return items[-limit:]

    def active_alerts(self, limit: int = 100) -> List[Alert]:
        return self.alerts(status="active", limit=limit)

    def acknowledge_alert(self, alert_id: str) -> Optional[Alert]:
        with self._lock:
            a = self._alerts_by_id.get(alert_id)
            if a:
                a.status = "acknowledged"
            return a

    def recent_telemetry(self, window_s: int) -> List[Telemetry]:
        cutoff = _utcnow().timestamp() - window_s
        with self._lock:
            return [
                t for t in self._telemetry if t.timestamp.timestamp() >= cutoff
            ]

    def recent_vehicle_events(self, window_s: int) -> List[VehicleEvent]:
        cutoff = _utcnow().timestamp() - window_s
        with self._lock:
            return [
                e for e in self._vehicle_events if e.timestamp.timestamp() >= cutoff
            ]

    # ----------------------- simulation status ------------------------- #
    def simulation_status(self) -> dict:
        with self._lock:
            last = self._sim_last_seen
            counts = dict(self._sim_counts)
        if last is None:
            return {
                "connected": False,
                "state": "waiting_for_feeder",
                "last_seen": None,
                "seconds_since_last": None,
                "counts": counts,
            }
        age = _utcnow().timestamp() - last.timestamp()
        return {
            "connected": age <= config.SIM_STALE_AFTER_S,
            "state": "live" if age <= config.SIM_STALE_AFTER_S else "stale",
            "last_seen": last.isoformat(),
            "seconds_since_last": round(age, 1),
            "counts": counts,
        }


store = DataStore()
