# main.py
"""
Entrypoint for the multiplaform bridge inbox bot.
Starts the Discord bot and platform connectors (Telegram + stubs).
"""
import os
import asyncio
from dotenv import load_dotenv
from database import Database
from discord_bot import DiscordBridge
from platforms.telegram import TelegramPlatform
from platforms.whatsapp import WhatsAppPlatform
from platforms.instagram import InstagramPlatform
from platforms.facebook import FacebookPlatform
from platforms.snapchat import SnapchatPlatform
from platforms.tiktok import TikTokPlatform

load_dotenv()

async def main():
    # Load config from environment
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID")) if os.getenv("DISCORD_GUILD_ID") else None
    DISCORD_ADMIN_ID = int(os.getenv("DISCORD_ADMIN_ID")) if os.getenv("DISCORD_ADMIN_ID") else None

    if not DISCORD_TOKEN or not DISCORD_GUILD_ID or not DISCORD_ADMIN_ID:
        print("Missing DISCORD_TOKEN, DISCORD_GUILD_ID or DISCORD_ADMIN_ID in environment. Exiting.")
        return

    # Initialize DB
    db = Database(os.getenv("DATABASE_PATH", "./data/bot.db"))

    # Start Discord
    discord = DiscordBridge(db=db, guild_id=DISCORD_GUILD_ID, admin_id=DISCORD_ADMIN_ID)
    await discord.start(DISCORD_TOKEN)  # this will run until bot is ready

    # Register platforms
    telegram = TelegramPlatform(token=os.getenv("TELEGRAM_TOKEN"), discord=discord, db=db)
    # Register platform handlers so Discord can route outbound messages
    discord.register_platform_handler("TL", telegram)

    # Start platform connectors (telegram is async and will run its own loop)
    await telegram.start()

    # Stubs for other platforms (not started by default)
    whatsapp = WhatsAppPlatform(discord=discord, db=db)
    instagram = InstagramPlatform(discord=discord, db=db)
    facebook = FacebookPlatform(discord=discord, db=db)
    snapchat = SnapchatPlatform(discord=discord, db=db)
    tiktok = TikTokPlatform(discord=discord, db=db)

    discord.register_platform_handler("WA", whatsapp)
    discord.register_platform_handler("IG", instagram)
    discord.register_platform_handler("FB", facebook)
    discord.register_platform_handler("SC", snapchat)
    discord.register_platform_handler("TK", tiktok)

    # Keep the process alive
    await discord.wait_until_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down")
