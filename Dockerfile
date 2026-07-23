# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# deps
# app
# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# Install pip requirements
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Basic healthcheck: verify process is running
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/bin/sh", "-c", "kill -0 1 || exit 1"]

CMD ["python", "main.py"]
