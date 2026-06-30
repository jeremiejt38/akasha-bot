import os
import base64
import logging
from aiohttp import web

logger = logging.getLogger(__name__)

class WebhookServer:
    def __init__(self, discord, instagram=None):
        self.discord = discord
        self.instagram = instagram
        self.host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
        self.port = int(os.getenv("WEBHOOK_PORT", "8000"))
        self.api_token = os.getenv("BRIDGE_API_TOKEN", "")
        self.meta_verify_token = os.getenv("META_VERIFY_TOKEN", "")
        self.runner = None
        self.site = None

    def _check_auth(self, request: web.Request) -> bool:
        if not self.api_token:
            return True
        auth = request.headers.get("Authorization", "")
        return auth == f"Bearer {self.api_token}"

    async def whatsapp_webhook(self, request: web.Request):
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            payload = await request.json()
            platform = payload.get("platform", "WA")
            platform_user_id = payload["platform_user_id"]
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
            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Failed handling WhatsApp webhook")
            return web.json_response({"error": "internal_error"}, status=500)

    async def meta_webhook_verify(self, request: web.Request):
        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        if mode == "subscribe" and token and token == self.meta_verify_token:
            logger.info("Meta webhook verification succeeded")
            return web.Response(text=challenge or "")

        logger.warning("Meta webhook verification failed")
        return web.Response(status=403, text="forbidden")

    async def meta_webhook(self, request: web.Request):
        try:
            payload = await request.json()
            logger.info("Meta webhook payload received")
            if self.instagram:
                await self.instagram.handle_webhook(payload)
            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Failed handling Meta webhook")
            return web.json_response({"error": "internal_error"}, status=500)

    async def health(self, request: web.Request):
        return web.json_response({"ok": True})

    async def start(self):
        app = web.Application()
        app.router.add_post("/webhooks/whatsapp", self.whatsapp_webhook)
        app.router.add_get("/webhooks/meta", self.meta_webhook_verify)
        app.router.add_post("/webhooks/meta", self.meta_webhook)
        app.router.add_get("/health", self.health)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        logger.info("Webhook server started on %s:%s", self.host, self.port)

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
