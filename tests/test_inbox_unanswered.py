import asyncio
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Database


def test_unanswered_inbox_conversation_lifecycle():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            db = Database(os.path.join(directory, "bot.db"))
            await db.connect()

            assert await db.record_unanswered_inbox_conversation("42", "WA", "user-1", "Bonjour")
            assert not await db.record_unanswered_inbox_conversation("42", "WA", "user-1", "Toujours là")

            reminders = await db.get_unanswered_inbox_reminders(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=25)
            )
            assert len(reminders) == 1
            assert reminders[0]["last_message_text"] == "Toujours là"

            await db.resolve_unanswered_inbox_conversation("42")
            reminders = await db.get_unanswered_inbox_reminders(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=25)
            )
            assert reminders == []

            assert await db.record_unanswered_inbox_conversation("42", "WA", "user-1", "Nouvelle conversation")
            await db.conn.close()

    asyncio.run(run())
