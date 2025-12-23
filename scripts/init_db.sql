-- ALPR Database Initialization Script
-- Creates schema for storing license plate detection events
-- Uses TimescaleDB for time-series optimization

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Drop existing table if exists (for clean reinstall)
DROP TABLE IF EXISTS plate_events CASCADE;

-- Create plate_events table
-- Stores all validated and deduplicated plate detection events
CREATE TABLE plate_events (
    -- Primary identifiers
    event_id UUID NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,

    -- Source information
    camera_id VARCHAR(50) NOT NULL,
    track_id VARCHAR(50) NOT NULL,

    -- Plate information
    plate_text VARCHAR(20) NOT NULL,              -- Original OCR text
    plate_normalized_text VARCHAR(20) NOT NULL,   -- Normalized/cleaned text
    plate_confidence FLOAT NOT NULL,              -- OCR confidence (0.0-1.0)
    plate_region VARCHAR(10) NOT NULL,            -- Region code (US-FL, US-CA, etc.)

    -- Vehicle information
    vehicle_type VARCHAR(20),                     -- car, truck, motorcycle, etc.
    vehicle_make VARCHAR(50),                     -- Vehicle manufacturer
    vehicle_model VARCHAR(50),                    -- Vehicle model
    vehicle_color VARCHAR(30),                    -- Vehicle color

    -- Image references
    plate_image_url TEXT,                         -- Path to saved plate crop
    vehicle_image_url TEXT,                       -- Path to saved vehicle crop
    frame_image_url TEXT,                         -- Path to saved frame

    -- Processing metadata
    latency_ms INTEGER,                           -- Processing latency
    quality_score FLOAT,                          -- Plate quality score
    frame_number INTEGER,                         -- Frame number in stream

    -- Location metadata
    site_id VARCHAR(50),                          -- Site/datacenter identifier
    host_id VARCHAR(100),                         -- Host machine identifier
    roi VARCHAR(50),                              -- Region of interest
    direction VARCHAR(20),                        -- Direction of travel

    -- Indexing
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Composite primary key (required for TimescaleDB hypertables)
    PRIMARY KEY (event_id, captured_at)
);

-- Convert to TimescaleDB hypertable (partitioned by time)
-- This optimizes for time-series queries and automatic data retention
SELECT create_hypertable('plate_events', 'captured_at', if_not_exists => TRUE);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_plate_normalized ON plate_events (plate_normalized_text, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_camera_time ON plate_events (camera_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_site_time ON plate_events (site_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_track_id ON plate_events (track_id);
CREATE INDEX IF NOT EXISTS idx_captured_at ON plate_events (captured_at DESC);

-- Create view for quick stats
CREATE OR REPLACE VIEW plate_events_stats AS
SELECT
    COUNT(*) as total_events,
    COUNT(DISTINCT plate_normalized_text) as unique_plates,
    COUNT(DISTINCT camera_id) as active_cameras,
    MIN(captured_at) as earliest_event,
    MAX(captured_at) as latest_event,
    AVG(plate_confidence) as avg_confidence,
    AVG(latency_ms) as avg_latency_ms
FROM plate_events;

-- Create view for recent events (last 24 hours)
CREATE OR REPLACE VIEW plate_events_recent AS
SELECT
    event_id,
    captured_at,
    camera_id,
    track_id,
    plate_normalized_text,
    plate_confidence,
    vehicle_type,
    vehicle_color,
    site_id
FROM plate_events
WHERE captured_at >= NOW() - INTERVAL '24 hours'
ORDER BY captured_at DESC;

-- Create materialized view for hourly aggregates (commented out - optional feature)
-- Uncomment to enable continuous aggregates for analytics
-- CREATE MATERIALIZED VIEW plate_events_hourly
-- WITH (timescaledb.continuous) AS
-- SELECT
--     time_bucket('1 hour', captured_at) AS hour,
--     camera_id,
--     site_id,
--     COUNT(*) as event_count,
--     COUNT(DISTINCT plate_normalized_text) as unique_plates,
--     AVG(plate_confidence) as avg_confidence,
--     AVG(latency_ms) as avg_latency_ms
-- FROM plate_events
-- GROUP BY hour, camera_id, site_id;
--
-- Add refresh policy for continuous aggregate (refresh every hour)
-- SELECT add_continuous_aggregate_policy('plate_events_hourly',
--     start_offset => INTERVAL '2 hours',
--     end_offset => INTERVAL '1 hour',
--     schedule_interval => INTERVAL '1 hour',
--     if_not_exists => TRUE);

-- Add data retention policy (optional - keep data for 90 days)
-- Uncomment to enable automatic data cleanup
-- SELECT add_retention_policy('plate_events', INTERVAL '90 days', if_not_exists => TRUE);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO alpr;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO alpr;

-- Insert test event to verify schema
INSERT INTO plate_events (
    event_id,
    captured_at,
    camera_id,
    track_id,
    plate_text,
    plate_normalized_text,
    plate_confidence,
    plate_region,
    vehicle_type,
    site_id,
    host_id
) VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    NOW(),
    'camera-01',
    't-1',
    'ABC-123',
    'ABC123',
    0.95,
    'US-FL',
    'car',
    'DC1',
    'jetson-orin-nx'
) ON CONFLICT (event_id, captured_at) DO NOTHING;
