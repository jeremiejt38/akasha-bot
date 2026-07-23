"""database.py
Async SQLite wrapper using aiosqlite to be safe in async contexts.
Provides async methods to get/set mappings between platform user IDs and Discord channel IDs.
"""
import os
import logging
import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str = "./data/bot.db"):
        self.path = path
        self.conn = None
        dirpath = os.path.dirname(self.path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        await self._init_schema()
        logger.debug("Database connected: %s", self.path)

    async def _init_schema(self):
        await self.conn.execute(
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
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                discord_id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                discord_username TEXT,
                overseerr_id INTEGER,
                overseerr_username TEXT,
                overseerr_plex_username TEXT,
                overseerr_discord_ids TEXT,
                wizarr_invite_code TEXT,
                wizarr_invite_expires TEXT,
                created_at TEXT,
                months_subscribed INTEGER DEFAULT 0,
                tracearr_user_id TEXT,
                tracearr_username TEXT,
                tracearr_trust_score REAL,
                tracearr_total_violations INTEGER,
                tracearr_session_count INTEGER,
                tracearr_last_activity TEXT,
                tracearr_stats TEXT,
                updated_at TEXT
            )
            """
        )
        await self.conn.commit()

    async def get_mapping(self, platform: str, platform_user_id: str):
        async with self.conn.execute(
            "SELECT discord_channel_id FROM mappings WHERE platform = ? AND platform_user_id = ?",
            (platform, platform_user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_mapping(self, platform: str, platform_user_id: str, discord_channel_id: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO mappings (platform, platform_user_id, discord_channel_id) VALUES (?, ?, ?)",
            (platform, platform_user_id, discord_channel_id),
        )
        await self.conn.commit()

    async def get_mapping_by_channel(self, discord_channel_id: int):
        async with self.conn.execute(
            "SELECT platform, platform_user_id FROM mappings WHERE discord_channel_id = ?",
            (discord_channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else None

    async def get_user_by_discord_id(self, discord_id: str):
        async with self.conn.execute(
            "SELECT * FROM users WHERE discord_id = ?",
            (discord_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_email(self, email: str):
        async with self.conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def set_user(self, **fields):
        columns = [
            "discord_id", "email", "discord_username", "overseerr_id",
            "overseerr_username", "overseerr_plex_username", "overseerr_discord_ids",
            "wizarr_invite_code", "wizarr_invite_expires", "created_at", "months_subscribed",
            "tracearr_user_id", "tracearr_username", "tracearr_trust_score",
            "tracearr_total_violations", "tracearr_session_count", "tracearr_last_activity",
            "tracearr_stats", "updated_at",
        ]
        values = {k: fields.get(k) for k in columns}
        keys = list(values.keys())
        placeholders = ", ".join("?" for _ in keys)
        cols = ", ".join(keys)
        sql = f"INSERT OR REPLACE INTO users ({cols}) VALUES ({placeholders})"
        await self.conn.execute(sql, tuple(values[k] for k in keys))
        await self.conn.commit()

    async def get_all_users(self):
        async with self.conn.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_user(self, discord_id: str, **fields):
        allowed = {
            "email", "discord_username", "overseerr_id", "overseerr_username",
            "overseerr_plex_username", "overseerr_discord_ids", "wizarr_invite_code",
            "wizarr_invite_expires", "created_at", "months_subscribed", "tracearr_user_id",
            "tracearr_username", "tracearr_trust_score", "tracearr_total_violations",
            "tracearr_session_count", "tracearr_last_activity", "tracearr_stats", "updated_at",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        sql = f"UPDATE users SET {set_clause} WHERE discord_id = ?"
        await self.conn.execute(sql, (*updates.values(), discord_id))
        await self.conn.commit()
