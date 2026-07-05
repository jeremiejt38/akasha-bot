"""platforms/facebook.py
Facebook Messenger connector using the Meta Messaging Graph API.
"""
import logging

from platforms.meta_common import MetaPlatform

logger = logging.getLogger(__name__)


class FacebookPlatform(MetaPlatform):
    """Facebook Messenger connector using the Meta Messaging Graph API.

    Requires a Facebook Page ID and a META_PAGE_ACCESS_TOKEN with the
    necessary messaging permissions.
    """

    def __init__(self, discord, db):
        super().__init__(discord, db, platform_tag="FB", page_id_env="FACEBOOK_PAGE_ID")

    async def start(self):
        await super().start()
