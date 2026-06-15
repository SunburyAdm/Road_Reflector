"""
Road-condition & traffic intelligence.

Derives alerts from telemetry and vehicle events. This logic is data-source agnostic:
it runs identically whether records come from the Python simulation feeder or from
real LoRaWAN / ChirpStack / MQTT decoders.

Thresholds are conservative demo defaults; tune freely.
"""
from __future__ import annotations

from typing import List, Optional

from . import config
from .schemas import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Telemetry,
    VehicleEvent,
)

# --- Thresholds ------------------------------------------------------------ #
ICE_RISK_TEMP_C = 1.0
LOW_BATTERY_PCT = 20.0
LOW_BATTERY_V = 3.05
HIGH_VIBRATION_PEAK_G = 1.2
POTHOLE_VIBRATION_ENERGY = 80.0
PARKING_CONGESTION_EVENTS = 12      # parking events within window
TRAFFIC_INCREASE_EVENTS = 18        # entry/exit events within window


def _alert(
    a_type: AlertType,
    severity: AlertSeverity,
    message: str,
    device_id: Optional[str] = None,
    segment_id: Optional[str] = None,
    is_simulated: bool = True,
) -> Alert:
    return Alert(
        type=a_type.value,
        severity=severity.value,
        status=AlertStatus.active.value,
        message=message,
        device_id=device_id,
        segment_id=segment_id,
        is_simulated=is_simulated,
    )


def evaluate_telemetry(t: Telemetry) -> List[Alert]:
    """Per-reading rules: water, ice, vibration, pothole, battery."""
    alerts: List[Alert] = []

    if t.surface_water:
        alerts.append(
            _alert(
                AlertType.surface_water,
                AlertSeverity.warning,
                f"Surface water detected at {t.device_id}.",
                t.device_id,
                t.segment_id,
                t.is_simulated,
            )
        )
        if t.pavement_temp_c is not None and t.pavement_temp_c <= ICE_RISK_TEMP_C:
            alerts.append(
                _alert(
                    AlertType.ice_risk,
                    AlertSeverity.critical,
                    f"Ice risk at {t.device_id}: water present and pavement "
                    f"{t.pavement_temp_c:.1f}°C.",
                    t.device_id,
                    t.segment_id,
                    t.is_simulated,
                )
            )
    elif t.pavement_temp_c is not None and t.pavement_temp_c <= ICE_RISK_TEMP_C:
        alerts.append(
            _alert(
                AlertType.ice_risk,
                AlertSeverity.warning,
                f"Sub-freezing pavement at {t.device_id}: "
                f"{t.pavement_temp_c:.1f}°C.",
                t.device_id,
                t.segment_id,
                t.is_simulated,
            )
        )

    if t.accel_peak_g is not None and t.accel_peak_g >= HIGH_VIBRATION_PEAK_G:
        alerts.append(
            _alert(
                AlertType.high_vibration,
                AlertSeverity.warning,
                f"High vibration at {t.device_id}: peak {t.accel_peak_g:.2f} g.",
                t.device_id,
                t.segment_id,
                t.is_simulated,
            )
        )

    if (
        t.vibration_energy is not None
        and t.vibration_energy >= POTHOLE_VIBRATION_ENERGY
    ):
        alerts.append(
            _alert(
                AlertType.possible_pothole,
                AlertSeverity.warning,
                f"Possible pothole / abnormal pavement vibration at {t.device_id} "
                f"(energy {t.vibration_energy:.0f}).",
                t.device_id,
                t.segment_id,
                t.is_simulated,
            )
        )

    low_v = t.battery_v is not None and t.battery_v <= LOW_BATTERY_V
    low_pct = t.battery_pct is not None and t.battery_pct <= LOW_BATTERY_PCT
    if low_v or low_pct:
        alerts.append(
            _alert(
                AlertType.low_battery,
                AlertSeverity.warning,
                f"Low battery on {t.device_id}: "
                f"{t.battery_pct if t.battery_pct is not None else '?'}% / "
                f"{t.battery_v if t.battery_v is not None else '?'} V.",
                t.device_id,
                t.segment_id,
                t.is_simulated,
            )
        )

    if str(t.device_status) in ("offline",):
        alerts.append(
            _alert(
                AlertType.device_offline,
                AlertSeverity.critical,
                f"Device {t.device_id} reported offline status.",
                t.device_id,
                t.segment_id,
                t.is_simulated,
            )
        )

    return alerts


def evaluate_vehicle_event(e: VehicleEvent) -> List[Alert]:
    """Per-event rules: abnormal vibration."""
    alerts: List[Alert] = []
    if e.event_type == "abnormal_vibration_event" or (
        e.accel_peak_g is not None and e.accel_peak_g >= HIGH_VIBRATION_PEAK_G
    ):
        alerts.append(
            _alert(
                AlertType.high_vibration,
                AlertSeverity.warning,
                f"Abnormal vibration from vehicle event {e.vehicle_event_id} "
                f"on {e.segment_id or 'site'}.",
                None,
                e.segment_id,
                e.is_simulated,
            )
        )
    return alerts


def evaluate_traffic(store) -> List[Alert]:
    """
    Window-based traffic rules: parking congestion and entry/exit surges.
    Call periodically (e.g., on each vehicle event ingest).
    """
    alerts: List[Alert] = []
    events = store.recent_vehicle_events(config.TRAFFIC_WINDOW_S)

    parking = [
        e
        for e in events
        if e.event_type in ("vehicle_parking", "vehicle_turning_into_parking")
    ]
    entry_exit = [
        e
        for e in events
        if e.event_type in ("vehicle_entering_site", "vehicle_exiting_site")
    ]

    if len(parking) >= PARKING_CONGESTION_EVENTS:
        alerts.append(
            _alert(
                AlertType.parking_congestion,
                AlertSeverity.info,
                f"Parking congestion: {len(parking)} parking maneuvers in the "
                f"last {config.TRAFFIC_WINDOW_S}s.",
            )
        )

    if len(entry_exit) >= TRAFFIC_INCREASE_EVENTS:
        alerts.append(
            _alert(
                AlertType.entry_exit_traffic_increase,
                AlertSeverity.info,
                f"Entry/exit traffic increase: {len(entry_exit)} site movements in "
                f"the last {config.TRAFFIC_WINDOW_S}s.",
            )
        )

    return alerts
