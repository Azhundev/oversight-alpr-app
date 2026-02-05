FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY core_services/metrics/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY core_services/metrics/ /app/
COPY schemas/ /app/schemas/

# Create logs directory
RUN mkdir -p /app/logs

# Expose metrics port
EXPOSE 8006

# Run metrics consumer
CMD ["python", "-u", "metrics_consumer.py"]
