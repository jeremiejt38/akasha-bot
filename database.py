"""database.py
Helpers simples pour SQLite (initialisation et mapping).
"""
import os
import sqlite3

DB_PATH = os.getenv("DATABASE_PATH", "./data/bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    discord_channel_id INTEGER NOT NULL,
    display_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_user_id)
);
"""


def init_db(path: str = DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
