#!/usr/bin/env bash
set -euo pipefail

host="${UNRAID_HOST:-akasha-unraid}"
user="${UNRAID_USER:-root}"
project_dir="${UNRAID_PROJECT_DIR:-/mnt/user/appdata/akasha-bot}"
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
remote="${user}@${host}"

rsync -az --no-owner --no-group --delete \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude 'node_whatsapp/session/' \
  --exclude 'node_whatsapp/.wwebjs_auth/' \
  --exclude 'node_whatsapp/node_modules/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude '.pytest_cache/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "${source_dir}/" "${remote}:${project_dir}/"

ssh "${remote}" "cd '${project_dir}' && docker compose up -d --build --remove-orphans && docker compose ps"
