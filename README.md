# multibridhe-inbox-discord-bot

Bot Discord Python servant de bridge de messagerie unifié.

Ce dépôt contient le scaffold initial et les stubs pour les plateformes prioritaires (Telegram en priorité).

Sommaire
- README en français
- structure modulaire dans platforms/
- .env.example
- Dockerfile + docker-compose.yml

Voir les issues pour la feuille de route.
# README.md

Multiplaform Bridge Inbox - minimal scaffold

This repository provides a scaffold for a Discord-based unified inbox bot. The bot:
- Ensures a Discord category named INBOX exists
- Creates/reuses per-user channels using a platform prefix (e.g. [TL]jean)
- Forwards inbound messages from platforms to Discord
- Forwards admin replies in Discord back to the correct platform

Included in this scaffold:
- Discord core (discord_bot.py)
- SQLite mapping (database.py)
- Telegram integration (platforms/telegram.py) using python-telegram-bot v20 (async)
- Stubs for WhatsApp/Instagram/Facebook/Snapchat/TikTok
- Dockerfile and docker-compose.yml

Quick start (development):
1. Copy `.env.example` to `.env` and fill tokens/IDs (Discord token, guild id, admin id, telegram token)
2. Build and run with Docker Compose:
   docker-compose up --build

Telegram usage:
- The Telegram connector uses polling (not webhook) and requires TELEGRAM_TOKEN.
- Messages sent to the Telegram bot will create or reuse a channel in the INBOX category and be posted there.
- Replies by the Discord admin (DISCORD_ADMIN_ID) inside the user's channel will be forwarded back to Telegram.

WhatsApp:
- The scaffold includes a placeholder for a whatsapp-web.js bridge in `./node_whatsapp`. Provide your own implementation if you want QR-based WhatsApp support.

Security:
- Do NOT commit real credentials. Use `.env` and secrets management for production.
- For unofficial platform integrations (WhatsApp/IG/FB/Snapchat/TikTok) prefer dedicated accounts.
