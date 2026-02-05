FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y gcc libffi-dev libssl-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY core_services/search/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY core_services/search/ /app/services/search/
COPY schemas/ /app/schemas/

RUN mkdir -p /app/logs

ENV PYTHONPATH=/app/services/search

EXPOSE 8004

CMD ["python", "-u", "/app/services/search/elasticsearch_consumer.py"]
