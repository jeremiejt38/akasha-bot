# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock* /app/
# Install pip requirements (fallback if not using poetry)
RUN pip install --no-cache-dir -U pip
RUN pip install --no-cache-dir python-dotenv discord.py python-telegram-bot

COPY . /app

CMD ["python", "main.py"]
