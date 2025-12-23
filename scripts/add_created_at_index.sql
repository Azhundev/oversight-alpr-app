-- Add index on created_at for efficient recent events queries
-- This optimizes the /events/recent endpoint which orders by created_at DESC

CREATE INDEX IF NOT EXISTS idx_created_at ON plate_events (created_at DESC);
