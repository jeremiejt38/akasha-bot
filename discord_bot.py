# discord_bot.py
"""
Discord bot that manages the INBOX category and channels mapping.
Listens for admin replies in the per-user channels and forwards them to the registered platform handlers.
"""
import asyncio
import discord
from discord.ext import commands

INBOX_CATEGORY_NAME = "INBOX"

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

        @self.bot.event
        async def on_ready():
            print(f"Discord bot ready as {self.bot.user}")
            self._ready_event.set()

        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore messages from the bot itself
            if message.author.id == self.bot.user.id:
                return

            # Only react to messages in the INBOX category
            if message.guild is None or message.guild.id != self.guild_id:
                return

            if message.author.id == self.admin_id:
                # Admin replied; forward to platform if we have mapping
                channel_id = message.channel.id
                mapping = self.db.get_mapping_by_channel(channel_id)
                if mapping:
                    platform, platform_user_id = mapping
                    handler = self.platform_handlers.get(platform)
                    if handler and hasattr(handler, 'send'):
                        # send text only for now
                        if message.content:
                            await handler.send(platform_user_id, message.content)
                        # TODO: support attachments/media
                return

            # For non-admin inbound messages in INBOX channels we don't act specially

    async def start(self, token: str):
        # Start the bot in background but wait until it is ready
        loop = asyncio.get_event_loop()
        # run bot in a background task
        task = loop.create_task(self.bot.start(token))
        await self._ready_event.wait()

    def register_platform_handler(self, platform_tag: str, handler):
        self.platform_handlers[platform_tag] = handler

    async def wait_until_closed(self):
        # keep alive until bot is closed
        await self.bot.wait_until_close()

    # Public API used by platform connectors to post inbound messages
    async def ensure_inbox_category(self):
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            # guild may not be in cache yet
            guild = await self.bot.fetch_guild(self.guild_id)
        # find category
        category = discord.utils.get(guild.categories, name=INBOX_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(INBOX_CATEGORY_NAME)
        return category

    async def get_or_create_channel_for(self, platform_tag: str, platform_user_id: str, display_name: str):
        # normalize channel name
        safe_name = display_name.lower().replace(' ', '-')
        channel_name = f"[{platform_tag}]{safe_name}"
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            guild = await self.bot.fetch_guild(self.guild_id)
        category = await self.ensure_inbox_category()
        # search for existing channel
        existing = discord.utils.get(category.text_channels, name=channel_name)
        if existing:
            # ensure mapping exists
            self.db.set_mapping(platform_tag, platform_user_id, existing.id)
            return existing
        # create channel
        channel = await guild.create_text_channel(channel_name, category=category)
        self.db.set_mapping(platform_tag, platform_user_id, channel.id)
        return channel

    async def post_inbound_message(self, platform_tag: str, platform_user_id: str, display_name: str, text: str):
        channel = await self.get_or_create_channel_for(platform_tag, platform_user_id, display_name)
        author = f"[{platform_tag}]{display_name}"
        await channel.send(f"**{author}**: {text}")

