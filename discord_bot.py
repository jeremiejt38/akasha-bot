"""discord_bot.py
Gestion minimale de la connexion Discord et de la catégorie INBOX.
- crée la catégorie INBOX si elle n'existe pas
- crée / réutilise des channels dans la catégorie
- intercept des messages de l'admin pour les relayer vers les plateformes (lookup DB)

Note: implémentation de base — à étendre.
"""
import os
import sqlite3
import asyncio
from discord.ext import commands
from discord import utils
from database import init_db, DB_PATH

INBOX_CATEGORY_NAME = "INBOX"
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
ADMIN_ID = int(os.getenv("DISCORD_ADMIN_ID", "0"))


class DiscordBridge(commands.Bot):
    def __init__(self):
        intents = discord_intents()
        super().__init__(command_prefix="!", intents=intents)
        init_db()
        self.db = sqlite3.connect(DB_PATH)

    async def setup_hook(self):
        # Called before on_ready
        pass

    async def on_ready(self):
        print(f"Logged in as {self.user} (id: {self.user.id})")
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            print("Guild not found; check DISCORD_GUILD_ID")
            return

        category = utils.get(guild.categories, name=INBOX_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(INBOX_CATEGORY_NAME)
            print("INBOX category created")
        self.inbox_category = category
        print("DiscordBridge ready")

    async def on_message(self, message):
        # Ignore messages from this bot
        if message.author.id == self.user.id:
            return
        # Handle only admin messages for outgoing relays
        if message.author.id != ADMIN_ID:
            return
        # Lookup mapping: channel -> (platform, platform_user_id)
        channel_id = message.channel.id
        cur = self.db.cursor()
        cur.execute(
            "SELECT platform, platform_user_id FROM mappings WHERE discord_channel_id = ?",
            (channel_id,),
        )
        row = cur.fetchone()
        if not row:
            # No mapping — ignore
            return
        platform, platform_user_id = row
        content = message.content
        # TODO: call the corresponding platform sender
        print(f"Outgoing to {platform}:{platform_user_id}: {content}")


def discord_intents():
    from discord import Intents

    intents = Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.guilds = True
    return intents
# discord_bot.py
"""
Discord bot that manages the INBOX category and channels mapping.
Listens for admin replies in the per-user channels and forwards them to the registered platform handlers.
"""
import asyncio
import logging
import discord
from discord.ext import commands

INBOX_CATEGORY_NAME = "INBOX"

logger = logging.getLogger(__name__)

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
        self.platform_handlers = {}  # map platform tag -> handler with send(platform_user_id, text)
        self._ready_event = asyncio.Event()
        self._closed = False
        self._bot_task = None

        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot ready as {self.bot.user}")
            self._ready_event.set()

        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore messages from the bot itself
            if message.author.id == self.bot.user.id:
                return

            # Only react to messages in the configured guild
            if message.guild is None or message.guild.id != self.guild_id:
                return

            if message.author.id == self.admin_id:
                # Admin replied; forward to platform if we have mapping
                channel_id = message.channel.id
                mapping = await self.db.get_mapping_by_channel(channel_id)
                if mapping:
                    platform, platform_user_id = mapping
                    handler = self.platform_handlers.get(platform)
                    if handler and hasattr(handler, 'send'):
                        # send text only for now
                        if message.content:
                            try:
                                await handler.send(platform_user_id, message.content)
                            except Exception as e:
                                logger.exception(f"Failed to forward admin message to platform {platform}: {e}")
                        # TODO: support attachments/media
                return

            # For non-admin inbound messages in INBOX channels we don't act specially

    async def start(self, token: str):
        # Start the bot in background but wait until it is ready
        loop = asyncio.get_event_loop()
        # run bot in a background task
        self._bot_task = loop.create_task(self.bot.start(token))
        await self._ready_event.wait()

    def register_platform_handler(self, platform_tag: str, handler):
        self.platform_handlers[platform_tag] = handler

    async def wait_until_closed(self):
        # wait for the bot task to finish
        if self._bot_task:
            try:
                await self._bot_task
            except asyncio.CancelledError:
                logger.info("Bot task was cancelled")
            except Exception:
                logger.exception("Bot task ended with exception")

    # Public API used by platform connectors to post inbound messages
    async def ensure_inbox_category(self):
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild is None:
                # guild may not be in cache yet
                guild = await self.bot.fetch_guild(self.guild_id)
            # find category
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
        # normalize channel name
        safe_name = display_name.lower().replace(' ', '-')
        # include short suffix from user id to avoid collisions
        suffix = str(platform_user_id)[-6:]
        channel_name = f"[{platform_tag}]{safe_name}-{suffix}"
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild is None:
                guild = await self.bot.fetch_guild(self.guild_id)
            category = await self.ensure_inbox_category()
            # search for existing channel
            existing = discord.utils.get(category.text_channels, name=channel_name)
            if existing:
                # ensure mapping exists
                await self.db.set_mapping(platform_tag, platform_user_id, existing.id)
                return existing
            # create channel
            channel = await guild.create_text_channel(channel_name, category=category)
            await self.db.set_mapping(platform_tag, platform_user_id, channel.id)
            return channel
        except discord.Forbidden:
            logger.exception("Bot lacks permission to create or access channel")
            raise
        except Exception:
            logger.exception("Failed to get or create channel")
            raise

    async def post_inbound_message(self, platform_tag: str, platform_user_id: str, display_name: str, text: str):
        try:
            channel = await self.get_or_create_channel_for(platform_tag, platform_user_id, display_name)
            author = f"[{platform_tag}]{display_name}"
            await channel.send(f"**{author}**: {text}")
        except Exception:
            logger.exception("Failed to post inbound message to Discord")
