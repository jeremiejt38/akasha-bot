# database.py
"""
Async SQLite wrapper using aiosqlite to be safe in async contexts.
Provides async methods to get/set mappings between platform user IDs and Discord channel IDs.
"""
import aiosqlite
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, path: str = "./data/bot.db"):
        self.path = path
        self.conn = None
        # ensure directory exists
        dirpath = os.path.dirname(self.path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        await self._init_schema()

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
        await self.conn.commit()

    async def get_channel(self, platform: str, platform_user_id: str):
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
