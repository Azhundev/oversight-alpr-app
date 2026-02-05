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
COPY core_services/storage/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir kafka-python loguru

# Copy application code
COPY core_services/storage/ ./services/storage/
COPY core_services/api/ ./services/api/
COPY shared/ ./shared/
COPY schemas/ ./schemas/

# Set Python path
ENV PYTHONPATH=/app

# Run the consumer (entrypoint handles JSON vs Avro based on USE_AVRO env var)
CMD ["python", "-u", "services/storage/consumer_entrypoint.py"]
