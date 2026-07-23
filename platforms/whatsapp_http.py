import os
import base64
import logging
import aiohttp

logger = logging.getLogger(__name__)

class WhatsAppHTTPPlatform:
    def __init__(self, discord, db):
        self.discord = discord
        self.db = db
        self.base_url = os.getenv("WHATSAPP_SERVICE_URL", "http://whatsapp:3001")
        self.api_token = os.getenv("BRIDGE_API_TOKEN", "")

    async def send(self, platform_user_id: str, text: str, attachments=None):
        logger.debug("Sending WhatsApp message to %s (text=%r, attachments=%s)", platform_user_id, text[:200], len(attachments) if attachments else 0)
        payload = {
            "platform_user_id": platform_user_id,
            "text": text or "",
            "attachments": []
        }

        if attachments:
            for att in attachments:
                try:
                    item = {
                        "filename": att.get("filename"),
                        "mime_type": att.get("content_type") or att.get("mime_type") or "application/octet-stream",
                    }
                    if "bytes" in att:
                        item["base64"] = base64.b64encode(att["bytes"]).decode("utf-8")
                    elif "path" in att:
                        with open(att["path"], "rb") as fh:
                            item["base64"] = base64.b64encode(fh.read()).decode("utf-8")
                    payload["attachments"].append(item)
                except Exception:
                    logger.exception("Failed to prepare WhatsApp attachment payload")

        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/send",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"WhatsApp send failed: {resp.status} {body}")
        except Exception:
            logger.exception("Failed to send outbound WhatsApp message")
            raise
