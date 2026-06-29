# README.md

Multiplaform Bridge Inbox - minimal scaffold

This repository provides a scaffold for a Discord-based unified inbox bot. The bot:
- Ensures a Discord category named INBOX exists
- Creates/reuses per-user channels using a platform prefix (e.g. [TL]jean)
- Forwards inbound messages from platforms to Discord
- Forwards admin replies in Discord back to the correct platform

Included in this scaffold:
- Discord core (discord_bot.py): manages INBOX category, per-user channels, forwards admin replies to platforms
- SQLite database wrapper (database.py) using aiosqlite for async safety
- Telegram integration (platforms/telegram.py) using python-telegram-bot v20 (async)
- Stubs for WhatsApp/Instagram/Facebook/Snapchat/TikTok
- Dockerfile and docker-compose.yml

Quick start (development):
1. Copy `.env.example` to `.env` and fill tokens/IDs (Discord token, guild id, admin id, telegram token)
2. Build and run with Docker Compose:
   docker-compose up --build

Telegram usage:
- The Telegram connector uses polling and requires TELEGRAM_TOKEN.
- Messages sent to the Telegram bot will create or reuse a channel in the INBOX category and be posted there.
- Replies by the Discord admin (DISCORD_ADMIN_ID) inside the user's channel will be forwarded back to Telegram.

WhatsApp (node bridge)
- The scaffold includes a placeholder for a whatsapp-web.js bridge in `./node_whatsapp`. Provide your own implementation if you want QR-based WhatsApp support.
- Typical flow: run the node_whatsapp service, scan the QR code once to establish a session, persist the session file so the QR is not needed again.
- Be aware that using non-official automation can lead to account bans; use dedicated accounts.

Notes on fixes applied
- Converted DB layer to use aiosqlite (async) to avoid concurrency issues.
- Fixed the discord bot lifecycle handling (wait_until_closed) and improved error handling around channel/category creation.
- Dockerfile updated to install pinned dependencies from requirements.txt and a basic HEALTHCHECK was added.

Security:
- Do NOT commit real credentials. Use `.env` and secrets management for production.

