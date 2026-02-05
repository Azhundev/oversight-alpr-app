# Dockerfile for ALPR Query API Service
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies including Docker CLI for service management
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    gnupg \
    lsb-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY core_services/api/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY core_services/storage/ ./services/storage/
COPY core_services/api/ ./services/api/
COPY shared/ ./shared/

# Copy service manager to root for import
COPY core_services/api/service_manager.py ./service_manager.py

# Set Python path
ENV PYTHONPATH=/app

# Expose API port
EXPOSE 8000

# Run the API server
CMD ["python", "-u", "services/api/query_api.py"]
