"""platforms/snapchat.py
Snapchat connector using an external HTTP bridge service.

There is no official public API for Snapchat direct messaging automation, so
this connector expects a separate service (e.g. a private automation proxy) at
SNAPCHAT_SERVICE_URL implementing the same /send + webhook contract as the
WhatsApp bridge.
"""
from platforms.external_http import ExternalHTTPPlatform


class SnapchatPlatform(ExternalHTTPPlatform):
    def __init__(self, discord, db):
        super().__init__(discord, db, platform_tag="SC", service_url_env="SNAPCHAT_SERVICE_URL")
