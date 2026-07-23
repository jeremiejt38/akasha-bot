"""database.py
Async SQLite wrapper using aiosqlite to be safe in async contexts.
Provides async methods to get/set mappings between platform user IDs and Discord channel IDs.
"""
import os
import logging
import datetime
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
        self.conn.row_factory = aiosqlite.Row
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
                admin_notes TEXT,
                renewal_requested_at TEXT,
                renewal_status TEXT,
                tracearr_user_id TEXT,
                tracearr_username TEXT,
                tracearr_trust_score REAL,
                tracearr_total_violations INTEGER,
                tracearr_session_count INTEGER,
                tracearr_last_activity TEXT,
                tracearr_stats TEXT,
                access_type TEXT DEFAULT 'subscriber',
                onboarding_answers TEXT,
                updated_at TEXT
            )
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                discord_id TEXT,
                admin_id TEXT,
                details TEXT,
                created_at TEXT
            )
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS problem_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT NOT NULL,
                discord_username TEXT NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT,
                media_type TEXT,
                media_id INTEGER,
                media_title TEXT,
                season_number INTEGER,
                episode_number INTEGER,
                episode_title TEXT,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                admin_response TEXT,
                admin_id TEXT,
                reported_at TEXT NOT NULL,
                resolved_at TEXT,
                admin_message_id INTEGER,
                admin_channel_id INTEGER,
                source TEXT NOT NULL DEFAULT 'discord',
                external_id TEXT
            )
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        await self._run_migrations()
        await self.conn.commit()

    async def _run_migrations(self):
        migrations = [
            ("001_legacy_users", self._migrate_legacy_users),
            ("002_problem_report_sources", self._migrate_problem_report_sources),
            ("003_account_notification_preferences", self._migrate_account_notification_preferences),
        ]
        async with self.conn.execute("SELECT version FROM schema_migrations") as cursor:
            applied = {row[0] for row in await cursor.fetchall()}
        for version, migration in migrations:
            if version in applied:
                continue
            await migration()
            await self.conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.datetime.utcnow().isoformat()),
            )
            logger.info("Applied database migration %s", version)

    async def _migrate_legacy_users(self):
        user_columns = {
            "email": "TEXT",
            "discord_username": "TEXT",
            "overseerr_id": "INTEGER",
            "overseerr_username": "TEXT",
            "overseerr_plex_username": "TEXT",
            "overseerr_discord_ids": "TEXT",
            "wizarr_invite_code": "TEXT",
            "wizarr_invite_expires": "TEXT",
            "created_at": "TEXT",
            "months_subscribed": "INTEGER DEFAULT 0",
            "admin_notes": "TEXT",
            "renewal_requested_at": "TEXT",
            "renewal_status": "TEXT",
            "tracearr_user_id": "TEXT",
            "tracearr_username": "TEXT",
            "tracearr_trust_score": "REAL",
            "tracearr_total_violations": "INTEGER",
            "tracearr_session_count": "INTEGER",
            "tracearr_last_activity": "TEXT",
            "tracearr_stats": "TEXT",
            "access_type": "TEXT DEFAULT 'subscriber'",
            "onboarding_answers": "TEXT",
            "updated_at": "TEXT",
        }
        for name, definition in user_columns.items():
            await self._ensure_user_column(name, definition)
        await self.conn.execute("UPDATE users SET access_type = 'subscriber' WHERE access_type IS NULL")

    async def _migrate_problem_report_sources(self):
        await self._ensure_problem_report_column("source", "TEXT NOT NULL DEFAULT 'discord'")
        await self._ensure_problem_report_column("external_id", "TEXT")
        await self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_problem_reports_source_external ON problem_reports(source, external_id) WHERE external_id IS NOT NULL")

    async def _migrate_account_notification_preferences(self):
        await self._ensure_user_column("dm_problem_notifications", "INTEGER NOT NULL DEFAULT 1")
        await self._ensure_user_column("dm_request_notifications", "INTEGER NOT NULL DEFAULT 1")

    async def _ensure_problem_report_column(self, name: str, definition: str):
        async with self.conn.execute("PRAGMA table_info(problem_reports)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if name not in columns:
            await self.conn.execute(f"ALTER TABLE problem_reports ADD COLUMN {name} {definition}")

    async def _ensure_user_column(self, name: str, definition: str):
        async with self.conn.execute("PRAGMA table_info(users)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if name not in columns:
            await self.conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

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

    async def get_user_by_overseerr_id(self, overseerr_id: int | str):
        async with self.conn.execute(
            "SELECT * FROM users WHERE overseerr_id = ?",
            (overseerr_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_plex_username(self, plex_username: str):
        async with self.conn.execute(
            "SELECT * FROM users WHERE LOWER(overseerr_plex_username) = LOWER(?)",
            (plex_username,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_notification_preferences(self, discord_id: str, **preferences):
        allowed = {"dm_problem_notifications", "dm_request_notifications"}
        values = {key: int(bool(value)) for key, value in preferences.items() if key in allowed}
        if values:
            await self.conn.execute(
                f"UPDATE users SET {', '.join(f'{key} = ?' for key in values)} WHERE discord_id = ?",
                (*values.values(), discord_id),
            )
            await self.conn.commit()

    async def set_user(self, **fields):
        columns = [
            "discord_id", "email", "discord_username", "overseerr_id",
            "overseerr_username", "overseerr_plex_username", "overseerr_discord_ids",
            "wizarr_invite_code", "wizarr_invite_expires", "created_at", "months_subscribed",
            "admin_notes", "renewal_requested_at", "renewal_status", "tracearr_user_id", "tracearr_username", "tracearr_trust_score",
            "tracearr_total_violations", "tracearr_session_count", "tracearr_last_activity",
            "tracearr_stats", "access_type", "onboarding_answers", "updated_at",
        ]
        values = {k: fields.get(k) for k in columns}
        keys = list(values.keys())
        placeholders = ", ".join("?" for _ in keys)
        cols = ", ".join(keys)
        sql = f"INSERT OR REPLACE INTO users ({cols}) VALUES ({placeholders})"
        await self.conn.execute(sql, tuple(values[k] for k in keys))
        await self.conn.commit()

    async def log_audit(self, action: str, discord_id: str | None = None, admin_id: str | None = None, details: str | None = None):
        now = datetime.datetime.utcnow().isoformat()
        await self.conn.execute(
            "INSERT INTO audit_logs (action, discord_id, admin_id, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (action, discord_id, admin_id, details, now),
        )
        await self.conn.commit()

    async def get_recent_audit_logs(self, limit: int = 20):
        async with self.conn.execute(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_users(self):
        async with self.conn.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def create_problem_report(self, **fields) -> int:
        columns = ["discord_id", "discord_username", "category", "subcategory", "media_type", "media_id", "media_title", "season_number", "episode_number", "episode_title", "description", "reported_at", "source", "external_id"]
        values = [fields.get(column) for column in columns]
        values[columns.index("source")] = fields.get("source") or "discord"
        async with self.conn.execute(
            f"INSERT INTO problem_reports ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values,
        ) as cursor:
            await self.conn.commit()
            return cursor.lastrowid

    async def update_problem_report(self, report_id: int, **fields):
        allowed = {"status", "admin_response", "admin_id", "resolved_at", "admin_message_id", "admin_channel_id", "description", "subcategory", "media_title", "discord_id", "discord_username"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if updates:
            await self.conn.execute(
                f"UPDATE problem_reports SET {', '.join(f'{key} = ?' for key in updates)} WHERE id = ?",
                (*updates.values(), report_id),
            )
            await self.conn.commit()

    async def get_problem_report_by_external_id(self, source: str, external_id: str):
        async with self.conn.execute("SELECT * FROM problem_reports WHERE source = ? AND external_id = ?", (source, external_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_problem_report(self, report_id: int):
        async with self.conn.execute("SELECT * FROM problem_reports WHERE id = ?", (report_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_problem_report_counts(self, discord_id: str):
        async with self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_count FROM problem_reports WHERE discord_id = ?",
            (discord_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return {"total": row[0] or 0, "open": row[1] or 0}

    async def get_problem_reports_for_user(self, discord_id: str):
        async with self.conn.execute("SELECT * FROM problem_reports WHERE discord_id = ? ORDER BY reported_at DESC LIMIT 20", (discord_id,)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_open_problem_reports(self):
        async with self.conn.execute("SELECT * FROM problem_reports WHERE status = 'open'") as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_problem_reports(self, status: str | None = None):
        query = "SELECT * FROM problem_reports"
        params = ()
        if status == "open":
            query += " WHERE status = 'open'"
        elif status == "closed":
            query += " WHERE status IN ('resolved', 'closed')"
        query += " ORDER BY reported_at DESC"
        async with self.conn.execute(query, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def record_access_grant(self, discord_id: str, code: str, expires: str | None, access_type: str):
        now = datetime.datetime.utcnow().isoformat()
        await self.conn.execute(
            """
            INSERT INTO users (discord_id, wizarr_invite_code, wizarr_invite_expires, access_type, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                wizarr_invite_code = excluded.wizarr_invite_code,
                wizarr_invite_expires = excluded.wizarr_invite_expires,
                access_type = excluded.access_type,
                updated_at = excluded.updated_at
            """,
            (discord_id, code, expires, access_type, now),
        )
        await self.conn.commit()

    async def record_onboarding_answers(self, discord_id: str, answers: str):
        now = datetime.datetime.utcnow().isoformat()
        await self.conn.execute(
            """
            INSERT INTO users (discord_id, onboarding_answers, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                onboarding_answers = excluded.onboarding_answers,
                updated_at = excluded.updated_at
            """,
            (discord_id, answers, now),
        )
        await self.conn.commit()

    async def update_user(self, discord_id: str, **fields):
        allowed = {
            "email", "discord_username", "overseerr_id", "overseerr_username",
            "overseerr_plex_username", "overseerr_discord_ids", "wizarr_invite_code",
            "wizarr_invite_expires", "created_at", "months_subscribed", "admin_notes",
            "renewal_requested_at", "renewal_status", "tracearr_user_id",
            "tracearr_username", "tracearr_trust_score", "tracearr_total_violations",
            "tracearr_session_count", "tracearr_last_activity", "tracearr_stats", "access_type", "onboarding_answers", "updated_at",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        sql = f"UPDATE users SET {set_clause} WHERE discord_id = ?"
        await self.conn.execute(sql, (*updates.values(), discord_id))
        await self.conn.commit()
