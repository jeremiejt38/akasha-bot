"""platforms/tiktok.py
TikTok connector using an external HTTP bridge service.

Official TikTok APIs do not offer direct DM sending for regular accounts, so
this connector expects a separate service (e.g. a private automation proxy) at
TIKTOK_SERVICE_URL implementing the same /send + webhook contract as the
WhatsApp bridge.
"""
from platforms.external_http import ExternalHTTPPlatform


class TikTokPlatform(ExternalHTTPPlatform):
    def __init__(self, discord, db):
        super().__init__(discord, db, platform_tag="TK", service_url_env="TIKTOK_SERVICE_URL")
