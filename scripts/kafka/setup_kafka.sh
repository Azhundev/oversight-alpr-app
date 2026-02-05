#!/bin/bash
# Setup Kafka with Docker and create ALPR topics

set -e  # Exit on error

echo "=== ALPR Kafka Setup ==="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Start Kafka cluster
echo "📦 Starting Kafka cluster..."
cd /home/jetson/OVR-ALPR
docker compose up -d

echo "⏳ Waiting for Kafka to be ready (30 seconds)..."
sleep 30

# Check if Kafka is healthy
echo "🔍 Checking Kafka health..."
if docker exec alpr-kafka kafka-broker-api-versions --bootstrap-server localhost:9092 > /dev/null 2>&1; then
    echo "✅ Kafka is healthy"
else
    echo "⚠️  Kafka might not be fully ready yet, continuing anyway..."
fi

echo ""
echo "📝 Creating ALPR topics..."

# Create main plate events topic
docker exec alpr-kafka kafka-topics \
    --create \
    --if-not-exists \
    --topic alpr.plates.detected \
    --bootstrap-server localhost:9092 \
    --partitions 3 \
    --replication-factor 1 \
    --config retention.ms=604800000 \
    --config compression.type=gzip

echo "✅ Created topic: alpr.plates.detected (3 partitions, 7 days retention)"

# Create vehicle tracking topic (optional)
docker exec alpr-kafka kafka-topics \
    --create \
    --if-not-exists \
    --topic alpr.vehicles.tracked \
    --bootstrap-server localhost:9092 \
    --partitions 2 \
    --replication-factor 1 \
    --config retention.ms=172800000 \
    --config compression.type=gzip

echo "✅ Created topic: alpr.vehicles.tracked (2 partitions, 2 days retention)"

# Create system health topic (optional)
docker exec alpr-kafka kafka-topics \
    --create \
    --if-not-exists \
    --topic alpr.system.health \
    --bootstrap-server localhost:9092 \
    --partitions 1 \
    --replication-factor 1 \
    --config retention.ms=86400000 \
    --config compression.type=gzip

echo "✅ Created topic: alpr.system.health (1 partition, 1 day retention)"

echo ""
echo "📋 Listing all topics:"
docker exec alpr-kafka kafka-topics --list --bootstrap-server localhost:9092

echo ""
echo "=== Kafka Setup Complete! ==="
echo ""
echo "Kafka is running at: localhost:9092"
echo "Kafka UI is available at: http://localhost:8080"
echo ""
echo "To view messages:"
echo "  docker exec -it alpr-kafka kafka-console-consumer \\"
echo "    --bootstrap-server localhost:9092 \\"
echo "    --topic alpr.plates.detected \\"
echo "    --from-beginning"
echo ""
echo "To stop Kafka:"
echo "  docker compose down"
echo ""
echo "To stop and remove all data:"
echo "  docker compose down -v"
echo ""
