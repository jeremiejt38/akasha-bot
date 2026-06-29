# platforms/telegram.py
"""
Telegram platform connector using python-telegram-bot v20 (async).
It receives messages from Telegram and forwards them to Discord via the DiscordBridge instance.
It also exposes a `send(platform_user_id, text, attachments=None)` coroutine used by Discord to send outbound messages.
"""
import asyncio
import logging
import io
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

class TelegramPlatform:
    def __init__(self, token: str, discord, db):
        self.token = token
        self.discord = discord
        self.db = db
        self.app = None

    async def start(self):
        if not self.token:
            logger.info("No TELEGRAM_TOKEN provided; Telegram platform not started.")
            return
        self.app = ApplicationBuilder().token(self.token).build()

        async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            user = update.effective_user
            user_id = str(user.id)
            display_name = user.first_name or str(user.id)
            text = update.message.text or ""

            attachments = []
            try:
                # Photos (list) - pick highest resolution
                if update.message.photo:
                    photo = update.message.photo[-1]
                    file = await context.bot.get_file(photo.file_id)
                    bio = io.BytesIO()
                    await file.download(out=bio)
                    bio.seek(0)
                    attachments.append({
                        'filename': f"photo_{photo.file_id}.jpg",
                        'bytes': bio.getvalue(),
                        'content_type': 'image/jpeg',
                    })

                # Document
                if update.message.document:
                    doc = update.message.document
                    file = await context.bot.get_file(doc.file_id)
                    bio = io.BytesIO()
                    await file.download(out=bio)
                    bio.seek(0)
                    attachments.append({
                        'filename': doc.file_name or f'doc_{doc.file_id}',
                        'bytes': bio.getvalue(),
                        'content_type': doc.mime_type,
                    })

                # Video
                if update.message.video:
                    vid = update.message.video
                    file = await context.bot.get_file(vid.file_id)
                    bio = io.BytesIO()
                    await file.download(out=bio)
                    bio.seek(0)
                    attachments.append({
                        'filename': f"video_{vid.file_id}.mp4",
                        'bytes': bio.getvalue(),
                        'content_type': 'video/mp4',
                    })

                # Audio
                if update.message.audio:
                    aud = update.message.audio
                    file = await context.bot.get_file(aud.file_id)
                    bio = io.BytesIO()
                    await file.download(out=bio)
                    bio.seek(0)
                    attachments.append({
                        'filename': aud.file_name or f'audio_{aud.file_id}',
                        'bytes': bio.getvalue(),
                        'content_type': aud.mime_type,
                    })

                # Voice
                if update.message.voice:
                    v = update.message.voice
                    file = await context.bot.get_file(v.file_id)
                    bio = io.BytesIO()
                    await file.download(out=bio)
                    bio.seek(0)
                    attachments.append({
                        'filename': f"voice_{v.file_id}.ogg",
                        'bytes': bio.getvalue(),
                        'content_type': 'audio/ogg',
                    })

            except Exception:
                logger.exception("Failed to download attachments from Telegram message")

            # forward to discord
            await self.discord.post_inbound_message("TL", user_id, display_name, text, attachments=attachments)

        self.app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))
        logger.info("Starting Telegram listener")
        await self.app.start()
        # Use run_polling in v20 for a proper lifecycle; start polling via updater
        await self.app.updater.start_polling()

    async def send(self, platform_user_id: str, text: str, attachments=None):
        # send a message back to the user via Telegram
        if not self.app:
            logger.warning("Telegram application not started; cannot send message")
            return
        chat_id = int(platform_user_id)
        try:
            # If attachments provided, send them (use send_document for generality)
            if attachments:
                for att in attachments:
                    try:
                        bio = io.BytesIO(att['bytes'])
                        bio.seek(0)
                        # Use send_document for generic files; caption = text for first
                        await self.app.bot.send_document(chat_id=chat_id, document=bio, filename=att.get('filename'), caption=text if att == attachments[0] else None)
                    except Exception:
                        logger.exception(f"Failed to send attachment to Telegram user {platform_user_id}")
                return

            # else just send text
            if text:
                await self.app.bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logger.exception(f"Failed to send Telegram message to {platform_user_id}")
