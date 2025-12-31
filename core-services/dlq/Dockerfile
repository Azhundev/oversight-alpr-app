FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY core-services/dlq/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY core-services/dlq/ /app/
COPY schemas/ /app/schemas/

# Create logs directory
RUN mkdir -p /app/logs

# Expose metrics port
EXPOSE 8005

# Run DLQ consumer
CMD ["python", "-u", "dlq_consumer.py"]
