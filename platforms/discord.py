import io
import os
import logging
import discord

logger = logging.getLogger(__name__)


class DiscordPlatform:
    def __init__(self, discord, db=None):
        self.discord = discord
        self.db = db

    async def send(self, platform_user_id: str, text: str, attachments=None):
        logger.debug(
            "Sending Discord DM to user %s (text=%r, attachments=%s)",
            platform_user_id,
            text[:200] if text else "",
            len(attachments) if attachments else 0,
        )
        try:
            user_id = int(platform_user_id)
            user = await self.discord.bot.fetch_user(user_id)
            if user is None:
                logger.warning("Discord user %s not found", platform_user_id)
                return

            files = []
            for att in (attachments or []):
                try:
                    if "bytes" in att:
                        bio = io.BytesIO(att["bytes"])
                        bio.seek(0)
                        filename = att.get("filename") or "file"
                        files.append(discord.File(fp=bio, filename=filename))
                    elif "path" in att:
                        files.append(
                            discord.File(
                                fp=att["path"],
                                filename=att.get("filename") or os.path.basename(att["path"]),
                            )
                        )
                except Exception:
                    logger.exception("Failed to prepare Discord attachment for user %s", platform_user_id)

            if files:
                await user.send(text or "", files=files)
            else:
                await user.send(text or "")
            logger.debug("Discord DM sent to user %s", platform_user_id)
        except Exception:
            logger.exception("Failed to send Discord DM to user %s", platform_user_id)
