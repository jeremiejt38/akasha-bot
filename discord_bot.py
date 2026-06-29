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
