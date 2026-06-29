# platforms/telegram.py
"""
Telegram platform connector using python-telegram-bot v20 (async).
It receives messages from Telegram and forwards them to Discord via the DiscordBridge instance.
It also exposes a `send(platform_user_id, text)` coroutine used by Discord to send outbound messages.
"""
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

class TelegramPlatform:
    def __init__(self, token: str, discord, db):
        self.token = token
        self.discord = discord
        self.db = db
        self.app = None

    async def start(self):
        if not self.token:
            print("No TELEGRAM_TOKEN provided; Telegram platform not started.")
            return
        self.app = ApplicationBuilder().token(self.token).build()

        async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            user = update.effective_user
            user_id = str(user.id)
            display_name = user.first_name or str(user.id)
            text = update.message.text or ""
            # forward to discord
            await self.discord.post_inbound_message("TL", user_id, display_name, text)

        self.app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))
        print("Starting Telegram listener")
        await self.app.start()
        await self.app.updater.start_polling()

    async def send(self, platform_user_id: str, text: str):
        # send a message back to the user via Telegram
        if not self.app:
            print("Telegram application not started; cannot send message")
            return
        try:
            chat_id = int(platform_user_id)
            await self.app.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            print(f"Failed to send Telegram message to {platform_user_id}: {e}")
