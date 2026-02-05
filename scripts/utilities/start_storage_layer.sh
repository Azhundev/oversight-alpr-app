#!/bin/bash
# Start ALPR Storage Layer Services
# This script starts TimescaleDB, Kafka Consumer, and Query API

set -e

echo "=== Starting ALPR Storage Layer ==="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi

# Start TimescaleDB container
echo "Starting TimescaleDB..."
docker compose up -d timescaledb

# Wait for TimescaleDB to be ready
echo "Waiting for TimescaleDB to be ready..."
for i in {1..30}; do
    if docker exec alpr-timescaledb pg_isready -U alpr -d alpr_db > /dev/null 2>&1; then
        echo "✅ TimescaleDB is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: TimescaleDB failed to start"
        exit 1
    fi
    sleep 1
done

# Verify database schema
echo "Verifying database schema..."
docker exec alpr-timescaledb psql -U alpr -d alpr_db -c "\dt" | grep -q plate_events
if [ $? -eq 0 ]; then
    echo "✅ Database schema initialized"
else
    echo "⚠️  Schema not found - should be created by init_db.sql"
fi

# Start Kafka Consumer (in background)
echo "Starting Kafka Consumer..."
python3 core_services/storage/kafka_consumer.py > logs/kafka_consumer.log 2>&1 &
CONSUMER_PID=$!
echo "Kafka Consumer started (PID: $CONSUMER_PID)"

# Start Query API (in background)
echo "Starting Query API..."
python3 core_services/api/query_api.py > logs/query_api.log 2>&1 &
API_PID=$!
echo "Query API started (PID: $API_PID)"

echo ""
echo "=== Storage Layer Started ==="
echo "TimescaleDB: localhost:5432"
echo "Query API: http://localhost:8000"
echo "Kafka Consumer: Running (PID: $CONSUMER_PID)"
echo ""
echo "Logs:"
echo "  - Kafka Consumer: logs/kafka_consumer.log"
echo "  - Query API: logs/query_api.log"
echo ""
echo "To stop services:"
echo "  - Kafka Consumer: kill $CONSUMER_PID"
echo "  - Query API: kill $API_PID"
echo "  - TimescaleDB: docker compose stop timescaledb"
