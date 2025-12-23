# Dockerfile for ALPR Query API Service
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/api/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/ ./services/
COPY shared/ ./shared/

# Set Python path
ENV PYTHONPATH=/app

# Expose API port
EXPOSE 8000

# Run the API server
CMD ["python", "-u", "services/api/query_api.py"]
