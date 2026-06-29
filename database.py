# database.py
"""
Simple SQLite wrapper for mapping platform users to Discord channel IDs.
"""
import sqlite3
import os

class Database:
    def __init__(self, path: str = "./data/bot.db"):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mappings (
                id INTEGER PRIMARY KEY,
                platform TEXT NOT NULL,
                platform_user_id TEXT NOT NULL,
                discord_channel_id INTEGER NOT NULL,
                UNIQUE(platform, platform_user_id)
            )
            """
        )
        self.conn.commit()

    def get_channel(self, platform: str, platform_user_id: str):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT discord_channel_id FROM mappings WHERE platform = ? AND platform_user_id = ?",
            (platform, platform_user_id),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def set_mapping(self, platform: str, platform_user_id: str, discord_channel_id: int):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO mappings (platform, platform_user_id, discord_channel_id) VALUES (?, ?, ?)",
            (platform, platform_user_id, discord_channel_id),
        )
        self.conn.commit()

    def get_mapping_by_channel(self, discord_channel_id: int):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT platform, platform_user_id FROM mappings WHERE discord_channel_id = ?",
            (discord_channel_id,)
        )
        row = cur.fetchone()
        return (row[0], row[1]) if row else None
