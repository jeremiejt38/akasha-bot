# Multiplaform Bridge Inbox - Discord unified inbox bot

Bot Discord Python servant de bridge de messagerie unifiée.

This bot centralizes inbound messages from several platforms (Telegram, WhatsApp, Instagram, Facebook Messenger, Snapchat, TikTok) into a single Discord server, creating one channel per user and per platform.

## What it does
- Ensures a Discord category named `INBOX` exists.
- Creates/reuses per-user channels using a platform marker (e.g. `tl-jean`, `wa-jean`).
- Forwards inbound messages from platforms to Discord (text + media where supported).
- Forwards admin replies in Discord back to the correct platform user.

## Supported platforms
- **Telegram**: text + media via `python-telegram-bot` v20.
- **WhatsApp**: separate Node bridge using `whatsapp-web.js`, with a low-power/energy-saving mode enabled by default.
- **Instagram**: Meta Messaging Graph API (webhook + reply).
- **Facebook Messenger**: Meta Messaging Graph API (webhook + reply).
- **Snapchat / TikTok**: HTTP bridge skeleton expecting a separate automation service at `SNAPCHAT_SERVICE_URL` / `TIKTOK_SERVICE_URL` (no official public DM API).

## Quick start
1. Copy `.env.example` to `.env` and fill in the required values.
2. Build and run with Docker Compose:
   ```bash
   docker compose up --build
   ```

## Development with Lando
The project can also be run with Lando. It starts a Python `bot` service (code mounted from the host) and a `whatsapp` service built from the existing `node_whatsapp/Dockerfile` (the WhatsApp code is baked into the image, so run `lando rebuild` after editing it).

1. Copy `.env.example` to `.env` and fill it in.
2. Start the environment:
   ```bash
   lando start
   ```
3. The webhook server is exposed at `https://multibridge-bot.lndo.site` (Lando proxy forwards to the bot's internal port `8000`).
4. Useful commands:
   ```bash
   lando check      # Python syntax check inside the bot container
   lando python     # run Python inside the bot container
   lando pip        # run pip inside the bot container
   lando rebuild    # rebuild services after changing WhatsApp code or Dockerfile
   ```

For plain Docker Compose usage, the project still provides a `docker-compose.yml` and a `docker-compose.override.yml` that loads `.env` into the containers.

## Tests / checks
Run syntax checks directly on the host (no Lando needed):

```bash
python3 -m py_compile main.py discord_bot.py database.py webhook_server.py platforms/*.py tests/*.py
node --check node_whatsapp/index.js
```

Run the small pytest suite:

```bash
pytest tests -q
```

## Debug mode
Set `DEBUG=true` in `.env` to enable verbose logging. In debug mode, the bot prints:

- startup configuration and enabled platforms
- every incoming webhook and its platform
- Discord admin replies being forwarded back to platforms
- channel resolution and creation
- full tracebacks for errors

## WhatsApp low-power mode
The WhatsApp bridge now runs Chromium with energy-saving flags (GPU disabled, no audio, no extensions, background networking disabled, etc.) and caps the Node.js heap. You can slow it down further with `WA_MESSAGE_PROCESS_DELAY_MS` or skip media downloads with `WA_SKIP_MEDIA`. See `.env.example` and `node_whatsapp/README.md` for details.

## Meta (Instagram & Facebook Messenger)

Configure the Meta webhook endpoint once for both platforms.

1. Create a Facebook App and enable **Messenger** and/or **Instagram** products.
2. Generate a **Page Access Token** (`META_PAGE_ACCESS_TOKEN`) for the linked Facebook Page.
3. Set `META_VERIFY_TOKEN` to a secret value used by Meta to verify the webhook URL.
4. Configure the webhook in the Meta Developer portal:
   - Callback URL: `https://<your-bot>/webhooks/meta`
   - Verify token: the value of `META_VERIFY_TOKEN`
   - Subscribe to `messages` and `messaging_postbacks` events.
5. For Instagram, set `INSTAGRAM_BUSINESS_ACCOUNT_ID` to the Instagram Business Account ID linked to the page.
6. For Facebook Messenger, set `FACEBOOK_PAGE_ID` to the page ID.

Inbound messages are routed automatically based on the webhook payload (`object: instagram` or `object: page`).

## Security
Do NOT commit real credentials. Use `.env` and a proper secrets manager for production.

