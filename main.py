import os
import asyncio
import logging
from dotenv import load_dotenv

from database import Database
from discord_bot import DiscordBridge
from platforms.telegram import TelegramPlatform
from platforms.whatsapp_http import WhatsAppHTTPPlatform
from platforms.instagram import InstagramPlatform
from platforms.facebook import FacebookPlatform
from platforms.snapchat import SnapchatPlatform
from platforms.tiktok import TikTokPlatform
from webhook_server import WebhookServer

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def _start_platform(platform_obj, name: str):
    try:
        await platform_obj.start()
    except Exception:
        logger.exception("Platform %s crashed during start", name)

async def main():
    discord_token = os.getenv("DISCORD_TOKEN")
    discord_guild_id = int(os.getenv("DISCORD_GUILD_ID")) if os.getenv("DISCORD_GUILD_ID") else None
    discord_admin_id = int(os.getenv("DISCORD_ADMIN_ID")) if os.getenv("DISCORD_ADMIN_ID") else None

    if not discord_token or not discord_guild_id or not discord_admin_id:
        logger.error("Missing DISCORD_TOKEN, DISCORD_GUILD_ID or DISCORD_ADMIN_ID in environment. Exiting.")
        return

    db = Database(os.getenv("DATABASE_PATH", "./data/bot.db"))
    await db.connect()

    discord = DiscordBridge(db=db, guild_id=discord_guild_id, admin_id=discord_admin_id)
    await discord.start(discord_token)

    telegram = TelegramPlatform(token=os.getenv("TELEGRAM_TOKEN"), discord=discord, db=db)
    discord.register_platform_handler("TL", telegram)

    whatsapp = WhatsAppHTTPPlatform(discord=discord, db=db)
    discord.register_platform_handler("WA", whatsapp)

    instagram = InstagramPlatform(discord=discord, db=db)
    discord.register_platform_handler("IG", instagram)

    webhook_server = WebhookServer(discord, instagram=instagram)
    await webhook_server.start()

    if os.getenv("TELEGRAM_TOKEN"):
        asyncio.create_task(_start_platform(telegram, "Telegram"))
    else:
        logger.info("TELEGRAM_TOKEN not set; Telegram connector will not be started.")

    asyncio.create_task(_start_platform(instagram, "Instagram"))

    facebook = FacebookPlatform(discord=discord, db=db)
    snapchat = SnapchatPlatform(discord=discord, db=db)
    tiktok = TikTokPlatform(discord=discord, db=db)

    discord.register_platform_handler("FB", facebook)
    discord.register_platform_handler("SC", snapchat)
    discord.register_platform_handler("TK", tiktok)

    await discord.wait_until_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down")
