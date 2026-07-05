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
from platforms.discord import DiscordPlatform
from integrations.wizarr_client import WizarrClient
from integrations.overseerr_client import OverseerrClient
from integrations.tracearr_client import TracearrClient
from webhook_server import WebhookServer

load_dotenv()


def _configure_logging():
    debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    return debug


DEBUG = _configure_logging()
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

    if DEBUG:
        logger.debug("Debug mode enabled")

    db = Database(os.getenv("DATABASE_PATH", "./data/bot.db"))
    await db.connect()
    logger.info("Database connected: %s", db.path)

    overseerr_client = OverseerrClient() if os.getenv("OVERSEERR_BASE_URL") else None
    wizarr_client = WizarrClient() if os.getenv("WIZARR_BASE_URL") else None
    tracearr_client = TracearrClient() if os.getenv("TRACEARR_BASE_URL") else None

    discord = DiscordBridge(
        db=db,
        guild_id=discord_guild_id,
        admin_id=discord_admin_id,
        overseerr_client=overseerr_client,
        wizarr_client=wizarr_client,
        tracearr_client=tracearr_client,
    )

    telegram = TelegramPlatform(token=os.getenv("TELEGRAM_TOKEN"), discord=discord, db=db)
    discord.register_platform_handler("TL", telegram)

    whatsapp = WhatsAppHTTPPlatform(discord=discord, db=db)
    discord.register_platform_handler("WA", whatsapp)

    instagram = InstagramPlatform(discord=discord, db=db)
    discord.register_platform_handler("IG", instagram)

    facebook = FacebookPlatform(discord=discord, db=db)
    discord.register_platform_handler("FB", facebook)

    snapchat = SnapchatPlatform(discord=discord, db=db)
    discord.register_platform_handler("SC", snapchat)

    tiktok = TikTokPlatform(discord=discord, db=db)
    discord.register_platform_handler("TK", tiktok)

    discord_platform = DiscordPlatform(discord=discord, db=db)
    discord.register_platform_handler("DC", discord_platform)

    logger.info(
        "Enabled platforms: Telegram=%s WhatsApp=%s Instagram=%s Messenger=%s Snapchat=%s TikTok=%s",
        bool(os.getenv("TELEGRAM_TOKEN")),
        True,
        bool(os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")),
        bool(os.getenv("FACEBOOK_PAGE_ID")),
        bool(os.getenv("SNAPCHAT_SERVICE_URL")),
        bool(os.getenv("TIKTOK_SERVICE_URL")),
    )

    logger.info("Starting Discord bot for guild_id=%s admin_id=%s", discord_guild_id, discord_admin_id)
    await discord.start(discord_token)

    webhook_server = WebhookServer(
        discord, instagram=instagram, facebook=facebook, snapchat=snapchat, tiktok=tiktok
    )
    await webhook_server.start()

    if os.getenv("TELEGRAM_TOKEN"):
        asyncio.create_task(_start_platform(telegram, "Telegram"))
    else:
        logger.info("TELEGRAM_TOKEN not set; Telegram connector will not be started.")

    asyncio.create_task(_start_platform(instagram, "Instagram"))
    asyncio.create_task(_start_platform(facebook, "Facebook"))
    asyncio.create_task(_start_platform(snapchat, "Snapchat"))
    asyncio.create_task(_start_platform(tiktok, "TikTok"))

    await discord.wait_until_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down")
