import json
import logging

from platforms.meta_client import MetaClient
from platforms.meta_common import extract_meta_entries

logger = logging.getLogger(__name__)

class InstagramPlatform:
    def __init__(self, discord, db):
        self.discord = discord
        self.db = db
        self.client = MetaClient()

    async def start(self):
        logger.info("Instagram platform scaffold initialized")

    async def handle_webhook(self, payload: dict):
        logger.info("Instagram webhook payload received: %s", json.dumps(payload)[:1000])
        entries = extract_meta_entries(payload)
        logger.info("Instagram webhook contains %d entries", len(entries))

    async def send(self, platform_user_id: str, text: str, attachments=None):
        logger.info("Instagram send scaffold invoked for user %s", platform_user_id)
        raise NotImplementedError("Instagram outbound send is not implemented yet")
