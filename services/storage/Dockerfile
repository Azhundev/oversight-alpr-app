# Dockerfile for ALPR Kafka Consumer Service
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/storage/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir kafka-python loguru

# Copy application code
COPY services/ ./services/
COPY shared/ ./shared/

# Set Python path
ENV PYTHONPATH=/app

# Run the consumer
CMD ["python", "-u", "services/storage/kafka_consumer.py"]
