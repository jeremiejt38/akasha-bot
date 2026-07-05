# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# app
# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
# Install pip requirements
RUN pip install --no-cache-dir -U pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Basic healthcheck: verify process is running
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/bin/sh", "-c", "pgrep -f 'python main.py' || exit 1"]

CMD ["python", "main.py"]
