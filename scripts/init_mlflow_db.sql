-- MLflow Database Initialization Script
-- Creates database and user for MLflow Model Registry
-- This script runs during TimescaleDB container initialization
-- File: scripts/init_mlflow_db.sql

-- Create MLflow user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mlflow') THEN
        CREATE ROLE mlflow WITH LOGIN PASSWORD 'mlflow_secure_pass';
        RAISE NOTICE 'Created mlflow user';
    ELSE
        RAISE NOTICE 'mlflow user already exists';
    END IF;
END
$$;

-- Create MLflow database if not exists
-- This requires running as postgres superuser
CREATE DATABASE mlflow_db;

-- Grant ownership and privileges
ALTER DATABASE mlflow_db OWNER TO mlflow;
GRANT ALL PRIVILEGES ON DATABASE mlflow_db TO mlflow;

-- Connect to mlflow_db and set up schema permissions
\connect mlflow_db

-- Grant schema privileges to mlflow user
GRANT ALL ON SCHEMA public TO mlflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO mlflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO mlflow;

-- Log completion
DO $$
BEGIN
    RAISE NOTICE '===========================================';
    RAISE NOTICE 'MLflow database initialization complete';
    RAISE NOTICE 'Database: mlflow_db';
    RAISE NOTICE 'User: mlflow';
    RAISE NOTICE 'Connection: postgresql://mlflow:mlflow_secure_pass@timescaledb:5432/mlflow_db';
    RAISE NOTICE '===========================================';
END
$$;
