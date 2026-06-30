# discord_bot.py
"""
Discord bot that manages the INBOX category and channels mapping.
Listens for admin replies in the per-user channels and forwards them to the registered platform handlers.

This version supports streaming large attachments to temporary files to avoid using too much memory,
and attempts emoji-based channel prefixes with a safe ASCII fallback.
"""
import asyncio
import logging
import io
import os
import re
import tempfile
import discord
from discord.ext import commands

INBOX_CATEGORY_NAME = os.getenv("INBOX_CATEGORY_NAME", "📥 INBOX")

logger = logging.getLogger(__name__)

THRESHOLD_MB = int(os.getenv("MAX_ATTACHMENT_MEMORY_MB", "5"))
THRESHOLD_BYTES = THRESHOLD_MB * 1024 * 1024

PLATFORM_CHANNEL_MARKERS = {
    "WA": os.getenv("CHANNEL_MARKER_WA", "🟢"),
    "TL": os.getenv("CHANNEL_MARKER_TL", "🔵"),
    "IG": os.getenv("CHANNEL_MARKER_IG", "🟣"),
    "FB": os.getenv("CHANNEL_MARKER_FB", "🔷"),
    "SC": os.getenv("CHANNEL_MARKER_SC", "🟡"),
    "TK": os.getenv("CHANNEL_MARKER_TK", "🔴"),
}

PLATFORM_ASCII_PREFIXES = {
    "WA": "wa",
    "TL": "tl",
    "IG": "ig",
    "FB": "fb",
    "SC": "sc",
    "TK": "tk",
}

class DiscordBridge:
    def __init__(self, db, guild_id: int, admin_id: int):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.db = db
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.platform_handlers = {}
        self._ready_event = asyncio.Event()
        self._closed = False
        self._bot_task = None

        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot ready as {self.bot.user}")
            self._ready_event.set()

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author.id == self.bot.user.id:
                return

            if message.guild is None or message.guild.id != self.guild_id:
                return

            if message.author.id == self.admin_id:
                channel_id = message.channel.id
                mapping = await self.db.get_mapping_by_channel(channel_id)
                if mapping:
                    platform, platform_user_id = mapping
                    handler = self.platform_handlers.get(platform)
                    if handler and hasattr(handler, 'send'):
                        attachments = []
                        for att in message.attachments:
                            try:
                                size = getattr(att, 'size', None) or 0
                                if size and size >= THRESHOLD_BYTES:
                                    tmp = tempfile.NamedTemporaryFile(delete=False)
                                    tmp.close()
                                    try:
                                        await att.save(tmp.name)
                                        attachments.append({
                                            'path': tmp.name,
                                            'filename': att.filename,
                                            'content_type': att.content_type,
                                        })
                                    except Exception:
                                        try:
                                            os.unlink(tmp.name)
                                        except Exception:
                                            pass
                                        raise
                                else:
                                    data = await att.read()
                                    attachments.append({
                                        'bytes': data,
                                        'filename': att.filename,
                                        'content_type': att.content_type,
                                    })
                            except Exception:
                                logger.exception(f"Failed to download attachment {getattr(att, 'url', '<unknown>')}")
                        if message.content or attachments:
                            try:
                                await handler.send(platform_user_id, message.content or "", attachments=attachments)
                            except Exception as e:
                                logger.exception(f"Failed to forward admin message to platform {platform}: {e}")
                return

    async def start(self, token: str):
        loop = asyncio.get_event_loop()
        self._bot_task = loop.create_task(self.bot.start(token))
        await self._ready_event.wait()

    def register_platform_handler(self, platform_tag: str, handler):
        self.platform_handlers[platform_tag] = handler

    async def wait_until_closed(self):
        if self._bot_task:
            try:
                await self._bot_task
            except asyncio.CancelledError:
                logger.info("Bot task was cancelled")
            except Exception:
                logger.exception("Bot task ended with exception")

    def _slugify_display_name(self, display_name: str) -> str:
        value = (display_name or "user").strip().lower()
        value = re.sub(r"\s+", "-", value)
        value = re.sub(r"[^a-z0-9\-]", "", value)
        value = re.sub(r"-+", "-", value).strip("-")
        return value or "user"

    def _build_channel_name_candidates(self, platform_tag: str, platform_user_id: str, display_name: str):
        safe_name = self._slugify_display_name(display_name)
        suffix = str(platform_user_id)[-6:]
        emoji_marker = PLATFORM_CHANNEL_MARKERS.get(platform_tag, platform_tag.lower())
        ascii_prefix = PLATFORM_ASCII_PREFIXES.get(platform_tag, platform_tag.lower())

        emoji_candidate = f"{emoji_marker}-{safe_name}-{suffix}".lower()
        ascii_candidate = f"{ascii_prefix}-{safe_name}-{suffix}".lower()
        return [emoji_candidate, ascii_candidate]

    async def ensure_inbox_category(self):
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild is None:
                guild = await self.bot.fetch_guild(self.guild_id)
            category = discord.utils.get(guild.categories, name=INBOX_CATEGORY_NAME)
            if category is None:
                category = await guild.create_category(INBOX_CATEGORY_NAME)
            return category
        except discord.Forbidden:
            logger.exception("Bot lacks permissions to manage channels/categories in the guild")
            raise
        except Exception:
            logger.exception("Failed to ensure INBOX category")
            raise

    async def get_or_create_channel_for(self, platform_tag: str, platform_user_id: str, display_name: str):
        candidates = self._build_channel_name_candidates(platform_tag, platform_user_id, display_name)
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild is None:
                guild = await self.bot.fetch_guild(self.guild_id)
            category = await self.ensure_inbox_category()

            for candidate_name in candidates:
                existing = discord.utils.get(category.text_channels, name=candidate_name)
                if existing:
                    await self.db.set_mapping(platform_tag, platform_user_id, existing.id)
                    return existing

            last_error = None
            for candidate_name in candidates:
                try:
                    channel = await guild.create_text_channel(candidate_name, category=category)
                    await self.db.set_mapping(platform_tag, platform_user_id, channel.id)
                    return channel
                except Exception as e:
                    last_error = e
                    logger.warning("Failed to create channel with name '%s', trying fallback if available", candidate_name)

            if last_error:
                raise last_error
            raise RuntimeError("Unable to create channel for unknown reason")
        except discord.Forbidden:
            logger.exception("Bot lacks permission to create or access channel")
            raise
        except Exception:
            logger.exception("Failed to get or create channel")
            raise

    async def post_inbound_message(self, platform_tag: str, platform_user_id: str, display_name: str, text: str, attachments=None):
        try:
            channel = await self.get_or_create_channel_for(platform_tag, platform_user_id, display_name)
            author = f"[{platform_tag}]{display_name}"
            files = []
            temp_paths = []
            if attachments:
                for att in attachments:
                    try:
                        if 'bytes' in att:
                            bio = io.BytesIO(att['bytes'])
                            bio.seek(0)
                            filename = att.get('filename') or 'file'
                            files.append(discord.File(fp=bio, filename=filename))
                        elif 'path' in att:
                            fp = open(att['path'], 'rb')
                            files.append(discord.File(fp=fp, filename=att.get('filename') or os.path.basename(att['path'])))
                            temp_paths.append({'path': att['path'], 'fp': fp})
                    except Exception:
                        logger.exception("Failed to prepare attachment for Discord")
            content = f"**{author}**: {text}" if text else f"**{author}**"
            if files:
                await channel.send(content, files=files)
            else:
                await channel.send(content)

            for t in temp_paths:
                try:
                    t['fp'].close()
                except Exception:
                    pass
                try:
                    os.unlink(t['path'])
                except Exception:
                    pass
        except Exception:
            logger.exception("Failed to post inbound message to Discord")
