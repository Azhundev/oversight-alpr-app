FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY core_services/alerting/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy alert engine code
COPY core_services/alerting/ /app/services/alerting/

# Copy schemas for Avro deserialization
COPY schemas/ /app/schemas/

# Create logs directory
RUN mkdir -p /app/logs

# Set Python path
ENV PYTHONPATH=/app/services/alerting

# Expose Prometheus metrics port
EXPOSE 8003

# Run alert engine
CMD ["python", "-u", "/app/services/alerting/alert_engine.py"]
