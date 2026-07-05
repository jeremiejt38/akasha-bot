import json
import logging
import os
import tempfile
from typing import List

import aiohttp

from platforms.meta_client import MetaClient

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_MEMORY_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENT_TOTAL_BYTES = 50 * 1024 * 1024


def extract_meta_entries(payload: dict):
    return payload.get("entry", []) if isinstance(payload, dict) else []


def detect_meta_platform(payload: dict) -> str | None:
    obj = payload.get("object") if isinstance(payload, dict) else None
    if obj == "instagram":
        return "instagram"
    if obj == "page":
        return "messenger"
    return None


class MetaPlatform:
    """Base class for Meta-based inbound/outbound connectors (Instagram, Facebook Messenger)."""

    def __init__(self, discord, db, platform_tag: str, page_id_env: str):
        self.discord = discord
        self.db = db
        self.platform_tag = platform_tag
        self.page_id = os.getenv(page_id_env, "")
        self.client = MetaClient()

    async def _get_display_name(self, user_id: str) -> str:
        fallback = f"{self.platform_tag} {user_id[-6:]}"
        if not self.page_id:
            return fallback
        try:
            fields = "name,username" if self.platform_tag == "IG" else "name,first_name,last_name"
            body = await self.client.get(f"/{user_id}", {"fields": fields})
            data = json.loads(body)
            return (
                data.get("username")
                or data.get("name")
                or " ".join(filter(None, [data.get("first_name"), data.get("last_name")]))
                or fallback
            )
        except Exception:
            logger.exception("Failed to fetch %s display name", self.platform_tag)
            return fallback

    async def _download_attachment(self, url: str, filename: str | None = None):
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"download failed: {resp.status}")
                content_type = resp.content_type or "application/octet-stream"
                total = 0
                chunks = bytearray()
                async for chunk in resp.content.iter_chunked(8192):
                    chunks.extend(chunk)
                    total += len(chunk)
                    if total > MAX_ATTACHMENT_MEMORY_BYTES:
                        break
                else:
                    return {
                        "bytes": bytes(chunks),
                        "filename": filename or "file",
                        "content_type": content_type,
                    }
                # Large attachment: stream to a temp file
                tmp = tempfile.NamedTemporaryFile(delete=False)
                try:
                    tmp.write(bytes(chunks))
                    async for chunk in resp.content.iter_chunked(8192):
                        tmp.write(chunk)
                        total += len(chunk)
                        if total > MAX_ATTACHMENT_TOTAL_BYTES:
                            raise RuntimeError("attachment exceeds 50 MB limit")
                    tmp.close()
                    return {
                        "path": tmp.name,
                        "filename": filename or "file",
                        "content_type": content_type,
                    }
                except Exception:
                    try:
                        tmp.close()
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    raise

    async def handle_webhook(self, payload: dict):
        entries = extract_meta_entries(payload)
        for entry in entries:
            for event in entry.get("messaging", []):
                message = event.get("message")
                if not message or message.get("is_echo"):
                    continue
                sender_id = event.get("sender", {}).get("id")
                if not sender_id:
                    continue
                text = message.get("text", "")
                attachments: List[dict] = []
                for att in message.get("attachments", []):
                    payload_data = att.get("payload", {})
                    url = payload_data.get("url")
                    if not url:
                        continue
                    try:
                        downloaded = await self._download_attachment(
                            url, filename=f"{att.get('type', 'file')}_media"
                        )
                        attachments.append(downloaded)
                    except Exception:
                        logger.exception("Failed to download %s attachment; appending URL as text", self.platform_tag)
                        text += f"\n[Attachment: {url}]"
                display_name = await self._get_display_name(sender_id)
                try:
                    await self.discord.post_inbound_message(
                        self.platform_tag, sender_id, display_name, text, attachments=attachments
                    )
                except Exception:
                    logger.exception("Failed to post %s inbound message to Discord", self.platform_tag)

    async def send(self, platform_user_id: str, text: str, attachments=None):
        logger.debug("Sending %s message to %s (text=%r, attachments=%s)", self.platform_tag, platform_user_id, text[:200], len(attachments) if attachments else 0)
        if not self.page_id:
            raise RuntimeError(f"{self.platform_tag} page/account ID not configured")
        if attachments:
            logger.warning("%s outbound attachments are not yet supported; sending text only", self.platform_tag)
        if not text:
            logger.warning("No text to send to %s; skipping message", self.platform_tag)
            return
        path = f"/{self.page_id}/messages"
        payload = {
            "recipient": {"id": platform_user_id},
            "messaging_type": "RESPONSE",
            "message": {"text": text or ""},
        }
        await self.client.post(path, payload)
