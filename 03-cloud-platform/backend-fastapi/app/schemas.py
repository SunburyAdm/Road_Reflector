"""
Pydantic schemas for the Smart Road Reflector Alpha Demonstration Platform.

These models are intentionally lenient so the Python simulation feeder (and, later,
real LoRaWAN / ChirpStack / MQTT decoders) can POST payloads without manual edits.
Only the fields needed to route and render an event are required; everything else is
optional with sensible defaults.

Sections:
  A. Telemetry  -> POST /v1/ingest/telemetry
  B. VehicleEvent -> POST /v1/ingest/vehicle-event
  C. Alert      -> POST /v1/ingest/alert
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enumerations (kept permissive: unknown strings are still accepted as plain   #
# strings on the wire because the ingestion models use str, not the Enum.)     #
# --------------------------------------------------------------------------- #
class DeviceStatus(str, Enum):
    ok = "ok"
    degraded = "degraded"
    low_battery = "low_battery"
    offline = "offline"


class VehicleClass(str, Enum):
    small_vehicle = "small_vehicle"
    medium_vehicle = "medium_vehicle"
    large_vehicle = "large_vehicle"
    delivery_van = "delivery_van"
    maintenance_truck = "maintenance_truck"
    unknown = "unknown"


class VehicleEventType(str, Enum):
    vehicle_entering_site = "vehicle_entering_site"
    vehicle_exiting_site = "vehicle_exiting_site"
    vehicle_passing_driveway = "vehicle_passing_driveway"
    vehicle_turning_into_parking = "vehicle_turning_into_parking"
    vehicle_parking = "vehicle_parking"
    vehicle_leaving_parking = "vehicle_leaving_parking"
    abnormal_vibration_event = "abnormal_vibration_event"


class AlertType(str, Enum):
    surface_water = "surface_water"
    ice_risk = "ice_risk"
    high_vibration = "high_vibration"
    possible_pothole = "possible_pothole"
    low_battery = "low_battery"
    device_offline = "device_offline"
    parking_congestion = "parking_congestion"
    entry_exit_traffic_increase = "entry_exit_traffic_increase"
    normal = "normal"


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(str, Enum):
    active = "active"
    acknowledged = "acknowledged"
    resolved = "resolved"


# --------------------------------------------------------------------------- #
# A. Sensor telemetry                                                          #
# --------------------------------------------------------------------------- #
class TelemetryIn(BaseModel):
    """Inbound telemetry payload (matches the simulation feeder output)."""

    site_id: str = "SITE-EAST-LIBERTY"
    device_id: str
    segment_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)

    device_status: str = DeviceStatus.ok.value
    battery_v: Optional[float] = None
    battery_pct: Optional[float] = None
    solar_v: Optional[float] = None

    pavement_temp_c: Optional[float] = None
    internal_temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    surface_water: Optional[bool] = None

    accel_rms: Optional[float] = None
    accel_peak_g: Optional[float] = None
    vibration_energy: Optional[float] = None
    tilt_deg: Optional[float] = None

    rssi: Optional[float] = None
    snr: Optional[float] = None

    model_config = {"extra": "allow"}


class Telemetry(TelemetryIn):
    """Stored telemetry record with platform-added metadata."""

    is_simulated: bool = True
    received_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# B. Vehicle event                                                            #
# --------------------------------------------------------------------------- #
class VehicleEventIn(BaseModel):
    vehicle_event_id: str = Field(default_factory=lambda: f"VEH-{uuid4().hex[:10]}")
    site_id: str = "SITE-EAST-LIBERTY"
    segment_id: Optional[str] = None
    path_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)

    event_type: str = VehicleEventType.vehicle_passing_driveway.value
    related_sensor_ids: List[str] = Field(default_factory=list)
    vehicle_class: str = VehicleClass.unknown.value
    direction: Optional[str] = None

    estimated_speed_kmh: Optional[float] = None
    estimated_length_m: Optional[float] = None
    estimated_axles: Optional[int] = None

    accel_peak_g: Optional[float] = None
    accel_rms: Optional[float] = None
    vibration_energy: Optional[float] = None
    confidence: Optional[float] = None

    model_config = {"extra": "allow"}


class VehicleEvent(VehicleEventIn):
    is_simulated: bool = True
    received_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# C. Alert                                                                    #
# --------------------------------------------------------------------------- #
class AlertIn(BaseModel):
    alert_id: str = Field(default_factory=lambda: f"ALR-{uuid4().hex[:10]}")
    site_id: str = "SITE-EAST-LIBERTY"
    device_id: Optional[str] = None
    segment_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)

    type: str = AlertType.normal.value
    severity: str = AlertSeverity.info.value
    status: str = AlertStatus.active.value
    message: str = ""

    model_config = {"extra": "allow"}


class Alert(AlertIn):
    is_simulated: bool = True
    received_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# WebSocket envelope                                                          #
# --------------------------------------------------------------------------- #
class StreamEvent(BaseModel):
    """Envelope broadcast over WS /v1/stream/events."""

    kind: str  # "telemetry" | "vehicle_event" | "alert" | "simulation_status"
    timestamp: datetime = Field(default_factory=_utcnow)
    data: dict


class IngestResponse(BaseModel):
    accepted: bool = True
    id: str
    kind: str
    derived_alerts: List[str] = Field(default_factory=list)
