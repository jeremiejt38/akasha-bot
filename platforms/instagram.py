import logging

from platforms.meta_common import MetaPlatform

logger = logging.getLogger(__name__)


class InstagramPlatform(MetaPlatform):
    """Instagram connector using the Meta Messaging Graph API.

    Requires an Instagram Business Account linked to a Facebook page and a
    META_PAGE_ACCESS_TOKEN with the necessary messaging permissions.
    """

    def __init__(self, discord, db):
        super().__init__(discord, db, platform_tag="IG", page_id_env="INSTAGRAM_BUSINESS_ACCOUNT_ID")

    async def start(self):
        logger.info("Instagram platform initialized (account_id=%s)", self.page_id or "not set")
