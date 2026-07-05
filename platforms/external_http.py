"""platforms/external_http.py
Generic HTTP bridge connector for platforms that rely on a separate service.

The connector sends outbound messages to the external service via POST /send
and receives inbound messages via a webhook payload matching the format used
by the WhatsApp bridge.
"""
import base64
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)


class ExternalHTTPPlatform:
    def __init__(self, discord, db, platform_tag: str, service_url_env: str, api_token_env: str = "BRIDGE_API_TOKEN"):
        self.discord = discord
        self.db = db
        self.platform_tag = platform_tag
        self.base_url = os.getenv(service_url_env, "").rstrip("/")
        self.api_token = os.getenv(api_token_env, "")
        self.enabled = bool(self.base_url)

    async def start(self):
        if not self.enabled:
            logger.info("%s service URL not set; %s connector disabled", self.platform_tag, self.platform_tag)

    async def send(self, platform_user_id: str, text: str, attachments=None):
        logger.debug("Sending %s message to %s (text=%r, attachments=%s)", self.platform_tag, platform_user_id, text[:200], len(attachments) if attachments else 0)
        if not self.enabled:
            logger.warning("%s service URL not configured; cannot send message", self.platform_tag)
            return

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
                    logger.exception("Failed to prepare %s attachment payload", self.platform_tag)

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
                        raise RuntimeError(f"{self.platform_tag} send failed: {resp.status} {body}")
        except Exception:
            logger.exception("Failed to send outbound %s message", self.platform_tag)

    async def handle_webhook(self, payload: dict):
        platform = payload.get("platform") or self.platform_tag
        platform_user_id = payload.get("platform_user_id")
        display_name = payload.get("display_name", platform_user_id)
        text = payload.get("text", "")
        attachments = []

        for att in payload.get("attachments", []):
            item = {
                "filename": att.get("filename"),
                "content_type": att.get("mime_type") or "application/octet-stream",
            }
            if att.get("base64"):
                item["bytes"] = base64.b64decode(att["base64"])
            elif att.get("path"):
                item["path"] = att["path"]
            attachments.append(item)

        await self.discord.post_inbound_message(
            platform, platform_user_id, display_name, text, attachments=attachments
        )
