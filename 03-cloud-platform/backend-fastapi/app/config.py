"""Runtime configuration and site-model loading."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

APP_DIR = Path(__file__).resolve().parent
SITE_CONFIG_PATH = Path(
    os.environ.get("SRR_SITE_CONFIG", APP_DIR / "data" / "site_east_liberty.json")
)

# How many recent records to keep in memory per stream (demo-friendly defaults).
TELEMETRY_BUFFER = int(os.environ.get("SRR_TELEMETRY_BUFFER", "5000"))
VEHICLE_EVENT_BUFFER = int(os.environ.get("SRR_VEHICLE_EVENT_BUFFER", "2000"))
ALERT_BUFFER = int(os.environ.get("SRR_ALERT_BUFFER", "1000"))

# Time-window (seconds) used by the road-condition / traffic intelligence.
TRAFFIC_WINDOW_S = int(os.environ.get("SRR_TRAFFIC_WINDOW_S", "120"))

# Seconds without telemetry before a device is considered offline.
DEVICE_OFFLINE_AFTER_S = int(os.environ.get("SRR_DEVICE_OFFLINE_AFTER_S", "90"))

# Seconds without any feeder activity before the simulation source is "stale".
SIM_STALE_AFTER_S = int(os.environ.get("SRR_SIM_STALE_AFTER_S", "20"))

CORS_ORIGINS = os.environ.get("SRR_CORS_ORIGINS", "*").split(",")


@lru_cache(maxsize=1)
def load_site_config() -> Dict[str, Any]:
    with open(SITE_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def sensor_index() -> Dict[str, Dict[str, Any]]:
    """device_id -> sensor definition."""
    cfg = load_site_config()
    return {s["device_id"]: s for s in cfg.get("sensors", [])}
