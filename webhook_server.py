import os
import asyncio
import base64
import logging
import threading
from aiohttp import web

from platforms.meta_common import detect_meta_platform

logger = logging.getLogger(__name__)

class WebhookServer:
    def __init__(self, discord, instagram=None, facebook=None, snapchat=None, tiktok=None):
        self.discord = discord
        self.instagram = instagram
        self.facebook = facebook
        self.snapchat = snapchat
        self.tiktok = tiktok
        self.host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
        self.port = int(os.getenv("WEBHOOK_PORT", "8000"))
        self.api_token = os.getenv("BRIDGE_API_TOKEN", "")
        self.meta_verify_token = os.getenv("META_VERIFY_TOKEN", "")
        self.plex_channel_id = os.getenv("PLEX_WEBHOOK_CHANNEL_ID")
        self.jellyfin_channel_id = os.getenv("JELLYFIN_WEBHOOK_CHANNEL_ID")
        self.overseerr_channel_id = os.getenv("OVERSEERR_WEBHOOK_CHANNEL_ID")
        self._main_loop = None
        self._server_thread = None

    async def _run_in_main(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
        return await asyncio.wrap_future(future)

    def _check_auth(self, request: web.Request) -> bool:
        if not self.api_token:
            return True
        auth = request.headers.get("Authorization", "")
        return auth == f"Bearer {self.api_token}"

    async def whatsapp_webhook(self, request: web.Request):
        logger.debug("WhatsApp webhook received from %s", request.remote)
        if not self._check_auth(request):
            logger.warning("WhatsApp webhook unauthorized from %s", request.remote)
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            payload = await request.json()
            logger.debug("WhatsApp payload: platform=%s user=%s", payload.get("platform", "WA"), payload.get("platform_user_id"))
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

            await self._run_in_main(
                self.discord.post_inbound_message(
                    platform, platform_user_id, display_name, text, attachments=attachments
                )
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
        logger.debug("Meta webhook received from %s", request.remote)
        try:
            payload = await request.json()
            platform = detect_meta_platform(payload)
            logger.info("Meta webhook payload received (platform=%s)", platform)
            logger.debug("Meta payload object=%s entries=%s", payload.get("object"), len(payload.get("entry", [])))
            if platform == "instagram" and self.instagram:
                await self._run_in_main(self.instagram.handle_webhook(payload))
            elif platform == "messenger" and self.facebook:
                await self._run_in_main(self.facebook.handle_webhook(payload))
            else:
                logger.info("Meta webhook received for unconfigured platform: %s", platform)
            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Failed handling Meta webhook")
            return web.json_response({"error": "internal_error"}, status=500)

    async def _generic_webhook(self, request: web.Request, handler, name: str):
        logger.debug("%s webhook received from %s", name, request.remote)
        if not self._check_auth(request):
            logger.warning("%s webhook unauthorized from %s", name, request.remote)
            return web.json_response({"error": "unauthorized"}, status=401)
        if not handler:
            logger.warning("%s webhook received but handler not configured", name)
            return web.json_response({"error": "not configured"}, status=503)
        try:
            payload = await request.json()
            await self._run_in_main(handler.handle_webhook(payload))
            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Failed handling %s webhook", name)
            return web.json_response({"error": "internal_error"}, status=500)

    async def snapchat_webhook(self, request: web.Request):
        return await self._generic_webhook(request, self.snapchat, "Snapchat")

    async def tiktok_webhook(self, request: web.Request):
        return await self._generic_webhook(request, self.tiktok, "TikTok")

    async def plex_webhook(self, request: web.Request):
        logger.debug("Plex webhook received from %s", request.remote)
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            payload = await request.json()
            event = payload.get("event")
            metadata = payload.get("Metadata", {})
            if event in ("library.new", "media.scrobble"):
                await self._run_in_main(
                    self.discord.post_media_notification(
                        channel_id=self.plex_channel_id,
                        source="Plex",
                        title=metadata.get("title"),
                        media_type=metadata.get("type"),
                        summary=metadata.get("summary"),
                        year=metadata.get("year"),
                        thumb=metadata.get("thumb"),
                    )
                )
            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Failed handling Plex webhook")
            return web.json_response({"error": "internal_error"}, status=500)

    async def jellyfin_webhook(self, request: web.Request):
        logger.debug("Jellyfin webhook received from %s", request.remote)
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            payload = await request.json()
            event_type = payload.get("Event") or payload.get("NotificationType")
            if event_type in ("ItemAdded", "PlaybackStart"):
                item = payload.get("Item", {})
                series = payload.get("Series", {})
                name = item.get("Name") or series.get("Name") or "Nouveau média"
                await self._run_in_main(
                    self.discord.post_media_notification(
                        channel_id=self.jellyfin_channel_id,
                        source="Jellyfin",
                        title=name,
                        media_type=item.get("Type"),
                        summary=item.get("Overview"),
                        year=item.get("ProductionYear"),
                        thumb=None,
                    )
                )
            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Failed handling Jellyfin webhook")
            return web.json_response({"error": "internal_error"}, status=500)

    async def overseerr_webhook(self, request: web.Request):
        logger.debug("Overseerr webhook received from %s", request.remote)
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            payload = await request.json()
            await self._run_in_main(self.discord.handle_overseerr_webhook(payload))
            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Failed handling Overseerr webhook")
            return web.json_response({"error": "internal_error"}, status=500)

    async def health(self, request: web.Request):
        return web.json_response({"ok": True})

    def _run_server(self):
        app = web.Application()
        app.router.add_post("/webhooks/whatsapp", self.whatsapp_webhook)
        app.router.add_get("/webhooks/meta", self.meta_webhook_verify)
        app.router.add_post("/webhooks/meta", self.meta_webhook)
        app.router.add_post("/webhooks/snapchat", self.snapchat_webhook)
        app.router.add_post("/webhooks/tiktok", self.tiktok_webhook)
        app.router.add_post("/webhooks/plex", self.plex_webhook)
        app.router.add_post("/webhooks/jellyfin", self.jellyfin_webhook)
        app.router.add_post("/webhooks/overseerr", self.overseerr_webhook)
        app.router.add_get("/health", self.health)
        web.run_app(app, host=self.host, port=self.port, handle_signals=False, print=None, access_log=None)

    async def start(self):
        self._main_loop = asyncio.get_running_loop()
        self._server_thread = threading.Thread(target=self._run_server, daemon=True, name="WebhookServer")
        self._server_thread.start()
        logger.info("Webhook server started on %s:%s", self.host, self.port)

    async def stop(self):
        # web.run_app is stopped automatically when the process exits
        pass
