#!/usr/bin/env bash
set -euo pipefail

DATABASE_PATH="${DATABASE_PATH:-./data/bot.db}"
BACKUP_DIR="${BACKUP_DIR:-./data/backups}"
RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-14}"

if [[ ! -f "$DATABASE_PATH" ]]; then
  echo "Database not found: $DATABASE_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/bot-${timestamp}.db"

python3 - "$DATABASE_PATH" "$target" <<'PY'
import sqlite3
import sys

source, target = sys.argv[1:]
source_db = sqlite3.connect(source)
target_db = sqlite3.connect(target)
try:
    source_db.backup(target_db)
    result = target_db.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result}")
finally:
    target_db.close()
    source_db.close()
PY

mapfile -t backups < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'bot-*.db' -printf '%T@ %p\n' | sort -nr | awk '{print $2}')
if (( ${#backups[@]} > RETENTION_COUNT )); then
  for backup in "${backups[@]:RETENTION_COUNT}"; do
    rm -f -- "$backup"
  done
fi

echo "Database backup created: $target"
