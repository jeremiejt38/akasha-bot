# platforms/telegram.py
"""
Telegram platform connector using python-telegram-bot v20 (async).
It receives messages from Telegram and forwards them to Discord via the DiscordBridge instance.
It also exposes a `send(platform_user_id, text, attachments=None)` coroutine used by Discord to send outbound messages.
This version writes large attachments to temporary files to avoid using too much memory.
"""
import asyncio
import logging
import io
import os
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

# Threshold (in bytes) for keeping attachments in memory vs writing to disk
THRESHOLD_MB = int(os.getenv("MAX_ATTACHMENT_MEMORY_MB", "5"))
THRESHOLD_BYTES = THRESHOLD_MB * 1024 * 1024

class TelegramPlatform:
    def __init__(self, token: str, discord, db):
        self.token = token
        self.discord = discord
        self.db = db
        self.app = None

    async def _download_file_maybe_to_disk(self, tg_file, suggested_name: str):
        """Download a telegram File either to memory (BytesIO) or to a temp file depending on size."""
        try:
            size = getattr(tg_file, 'file_size', None) or 0
        except Exception:
            size = 0

        if size and size < THRESHOLD_BYTES:
            bio = io.BytesIO()
            await tg_file.download(out=bio)
            bio.seek(0)
            return {'bytes': bio.getvalue(), 'filename': suggested_name}
        else:
            tmp = tempfile.NamedTemporaryFile(delete=False)
            tmp.close()
            try:
                await tg_file.download(out=tmp.name)
                return {'path': tmp.name, 'filename': suggested_name}
            except Exception:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
                raise

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
                # Photos (list) - pick highest resolution if present
                if update.message.photo:
                    photo = update.message.photo[-1]
                    file = await context.bot.get_file(photo.file_id)
                    got = await self._download_file_maybe_to_disk(file, f"photo_{photo.file_id}.jpg")
                    got['content_type'] = 'image/jpeg'
                    attachments.append(got)

                # Document
                if update.message.document:
                    doc = update.message.document
                    file = await context.bot.get_file(doc.file_id)
                    got = await self._download_file_maybe_to_disk(file, doc.file_name or f'doc_{doc.file_id}')
                    got['content_type'] = getattr(doc, 'mime_type', None)
                    attachments.append(got)

                # Video
                if update.message.video:
                    vid = update.message.video
                    file = await context.bot.get_file(vid.file_id)
                    got = await self._download_file_maybe_to_disk(file, f"video_{vid.file_id}.mp4")
                    got['content_type'] = 'video/mp4'
                    attachments.append(got)

                # Audio
                if update.message.audio:
                    aud = update.message.audio
                    file = await context.bot.get_file(aud.file_id)
                    got = await self._download_file_maybe_to_disk(file, aud.file_name or f'audio_{aud.file_id}')
                    got['content_type'] = getattr(aud, 'mime_type', None)
                    attachments.append(got)

                # Voice
                if update.message.voice:
                    v = update.message.voice
                    file = await context.bot.get_file(v.file_id)
                    got = await self._download_file_maybe_to_disk(file, f"voice_{v.file_id}.ogg")
                    got['content_type'] = 'audio/ogg'
                    attachments.append(got)

            except Exception:
                logger.exception("Failed to download attachments from Telegram message")

            # forward to discord
            try:
                await self.discord.post_inbound_message("TL", user_id, display_name, text, attachments=attachments)
            except Exception:
                logger.exception("Failed forwarding Telegram message to Discord")

        self.app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))
        logger.info("Starting Telegram listener")
        try:
            # IMPORTANT: for python-telegram-bot v20+, initialize before start
            await self.app.initialize()
            await self.app.start()
            # start polling (updater) after initialization/start
            await self.app.updater.start_polling()
            logger.info("Telegram listener started")
        except Exception:
            logger.exception("Telegram listener failed to start")
            # attempt a clean shutdown if partial initialization happened
            try:
                await self.app.updater.stop_polling()
            except Exception:
                pass
            try:
                await self.app.stop()
            except Exception:
                pass
            try:
                await self.app.shutdown()
            except Exception:
                pass

    async def send(self, platform_user_id: str, text: str, attachments=None):
        # send a message back to the user via Telegram
        if not self.app:
            logger.warning("Telegram application not started; cannot send message")
            return
        chat_id = int(platform_user_id)
        try:
            # If attachments provided, send them (use send_document for generality)
            if attachments:
                for idx, att in enumerate(attachments):
                    try:
                        caption = text if idx == 0 else None
                        if 'bytes' in att:
                            bio = io.BytesIO(att['bytes'])
                            bio.seek(0)
                            await self.app.bot.send_document(chat_id=chat_id, document=bio, filename=att.get('filename'), caption=caption)
                        elif 'path' in att:
                            with open(att['path'], 'rb') as fh:
                                await self.app.bot.send_document(chat_id=chat_id, document=fh, filename=att.get('filename'), caption=caption)
                            # cleanup temp file after sending
                            try:
                                os.unlink(att['path'])
                            except Exception:
                                pass
                    except Exception:
                        logger.exception(f"Failed to send attachment to Telegram user {platform_user_id}")
                return

            # else just send text
            if text:
                await self.app.bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logger.exception(f"Failed to send Telegram message to {platform_user_id}")
