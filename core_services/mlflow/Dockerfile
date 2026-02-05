# MLflow Server with PostgreSQL and S3 support
# For ALPR Model Registry

FROM ghcr.io/mlflow/mlflow:v2.9.2

# Install curl for health checks and Python dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir psycopg2-binary boto3

# Default port
EXPOSE 5000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1
