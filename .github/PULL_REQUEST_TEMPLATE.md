# Pull request template

Title: Initial scaffold: Discord bridge core + Telegram integration

This PR adds the initial scaffold for the multiplaform bridge inbox bot.

Summary:
- Discord core (discord_bot.py): manages INBOX category, per-user channels, forwards admin replies to platforms
- SQLite database wrapper (database.py) for mappings
- Telegram integration (platforms/telegram.py) using python-telegram-bot v20 (async)
- Stubs for WhatsApp/Instagram/Facebook/Snapchat/TikTok in platforms/
- Dockerfile and docker-compose.yml (optional whatsapp node bridge service)
- .env.example and README

Notes:
- No secrets are committed. Fill .env from .env.example.
- WhatsApp is a placeholder; run a whatsapp-web.js bridge if you need WhatsApp support.
