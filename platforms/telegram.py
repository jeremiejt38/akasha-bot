"""platforms/telegram.py
Implémentation initiale pour Telegram via python-telegram-bot.
Gère le flux entrant (Telegram -> Discord).
"""
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from database import init_db, DB_PATH

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Ce module expose une fonction start(dispatcher, discord_bridge) pour se connecter

async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Exemple minimal: on récupère l'utilisateur et le message
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = update.message.text if update.message else ""
    # TODO: lookup/create Discord channel mapping, then post message via discord_bridge
    print(f"Telegram message from {user.username or user.full_name}: {text}")


def start(discord_bridge):
    """Démarre le listener Telegram dans une nouvelle Task/Thread.
    Passer le discord_bridge (instance) pour poster dans Discord.
    """
    if not TELEGRAM_TOKEN:
        logging.warning("TELEGRAM_TOKEN not set; skipping Telegram bridge")
        return
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    # run in background
    import threading

    t = threading.Thread(target=app.run_polling, daemon=True)
    t.start()
