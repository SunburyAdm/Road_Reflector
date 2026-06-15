-- =====================================================================
-- Smart Road Reflector — Alpha Demonstration Platform
-- Database schema: PostgreSQL (metadata + events) + TimescaleDB (telemetry)
-- =====================================================================
-- The Alpha demo backend runs fully in-memory and does NOT require this
-- schema. It is the production persistence target: swap the methods in
-- backend-fastapi/app/store.py to read/write these tables. Telemetry is a
-- TimescaleDB hypertable; if TimescaleDB is unavailable, the table still
-- works as a plain PostgreSQL table (just drop the create_hypertable call).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "timescaledb";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------------ --
-- Reference / metadata (PostgreSQL)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS sites (
    site_id      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    address      TEXT,
    approx_lat   DOUBLE PRECISION,
    approx_lon   DOUBLE PRECISION,
    config       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gateways (
    gateway_id   TEXT PRIMARY KEY,
    site_id      TEXT REFERENCES sites(site_id),
    name         TEXT,
    model        TEXT,
    pos_x_m      DOUBLE PRECISION,
    pos_y_m      DOUBLE PRECISION,
    pos_z_m      DOUBLE PRECISION,
    last_seen    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS road_segments (
    segment_id      TEXT PRIMARY KEY,
    site_id         TEXT REFERENCES sites(site_id),
    name            TEXT,
    type            TEXT,                 -- entry_exit | driveway | parking_loop
    polyline_m      JSONB NOT NULL,       -- [[x,y], ...] meters
    width_m         DOUBLE PRECISION,
    speed_limit_kmh INTEGER
);

CREATE TABLE IF NOT EXISTS parking_zones (
    parking_zone_id TEXT PRIMARY KEY,
    site_id         TEXT REFERENCES sites(site_id),
    name            TEXT,
    capacity        INTEGER,
    anchor_x_m      DOUBLE PRECISION,
    anchor_y_m      DOUBLE PRECISION,
    config          JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS devices (
    device_id     TEXT PRIMARY KEY,       -- e.g. SRR-OFFICE-001
    site_id       TEXT REFERENCES sites(site_id),
    segment_id    TEXT REFERENCES road_segments(segment_id),
    gateway_id    TEXT REFERENCES gateways(gateway_id),
    role          TEXT,                   -- speed_direction | vehicle_count | surface_water | parking_condition
    pos_x_m       DOUBLE PRECISION,
    pos_y_m       DOUBLE PRECISION,
    pos_z_m       DOUBLE PRECISION,
    device_group  TEXT,
    is_simulated  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_consumers (
    consumer_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    api_key_hash  TEXT NOT NULL,
    scopes        TEXT[] NOT NULL DEFAULT '{}',
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS simulation_sources (
    source_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id       TEXT REFERENCES sites(site_id),
    label         TEXT,                   -- e.g. "python-feeder"
    last_seen     TIMESTAMPTZ,
    telemetry_count BIGINT NOT NULL DEFAULT 0,
    vehicle_event_count BIGINT NOT NULL DEFAULT 0,
    alert_count   BIGINT NOT NULL DEFAULT 0
);

-- ------------------------------------------------------------------ --
-- Time-series telemetry (TimescaleDB hypertable)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS sensor_telemetry (
    time             TIMESTAMPTZ NOT NULL,
    site_id          TEXT NOT NULL,
    device_id        TEXT NOT NULL,
    segment_id       TEXT,
    device_status    TEXT,
    battery_v        DOUBLE PRECISION,
    battery_pct      DOUBLE PRECISION,
    solar_v          DOUBLE PRECISION,
    pavement_temp_c  DOUBLE PRECISION,
    internal_temp_c  DOUBLE PRECISION,
    humidity_pct     DOUBLE PRECISION,
    surface_water    BOOLEAN,
    accel_rms        DOUBLE PRECISION,
    accel_peak_g     DOUBLE PRECISION,
    vibration_energy DOUBLE PRECISION,
    tilt_deg         DOUBLE PRECISION,
    rssi             DOUBLE PRECISION,
    snr              DOUBLE PRECISION,
    is_simulated     BOOLEAN NOT NULL DEFAULT TRUE
);

-- Make it a hypertable (no-op-safe if already done). Comment out if no TimescaleDB.
SELECT create_hypertable('sensor_telemetry', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
    ON sensor_telemetry (device_id, time DESC);

-- ------------------------------------------------------------------ --
-- Vehicle events (PostgreSQL)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS vehicle_events (
    vehicle_event_id   TEXT PRIMARY KEY,
    site_id            TEXT NOT NULL,
    segment_id         TEXT,
    path_id            TEXT,
    ts                 TIMESTAMPTZ NOT NULL,
    event_type         TEXT NOT NULL,
    related_sensor_ids TEXT[] NOT NULL DEFAULT '{}',
    vehicle_class      TEXT,
    direction          TEXT,
    estimated_speed_kmh DOUBLE PRECISION,
    estimated_length_m  DOUBLE PRECISION,
    estimated_axles     INTEGER,
    accel_peak_g        DOUBLE PRECISION,
    accel_rms           DOUBLE PRECISION,
    vibration_energy    DOUBLE PRECISION,
    confidence          DOUBLE PRECISION,
    is_simulated        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_vehicle_events_ts ON vehicle_events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_type ON vehicle_events (event_type);

-- Parking lot traffic events are a filtered view of vehicle_events.
CREATE OR REPLACE VIEW parking_traffic_events AS
SELECT *
FROM vehicle_events
WHERE event_type IN (
    'vehicle_turning_into_parking',
    'vehicle_parking',
    'vehicle_leaving_parking'
);

-- ------------------------------------------------------------------ --
-- Alerts (PostgreSQL)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS alerts (
    alert_id     TEXT PRIMARY KEY,
    site_id      TEXT NOT NULL,
    device_id    TEXT,
    segment_id   TEXT,
    ts           TIMESTAMPTZ NOT NULL,
    type         TEXT NOT NULL,         -- surface_water | ice_risk | high_vibration | ...
    severity     TEXT NOT NULL,         -- info | warning | critical
    status       TEXT NOT NULL,         -- active | acknowledged | resolved
    message      TEXT,
    is_simulated BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
