import asyncio
import logging
import os

logger = logging.getLogger(__name__)


class InvitationIdentitySync:
    def __init__(self, bridge):
        self.bridge = bridge
        self.interval_seconds = max(30, int(os.getenv("WIZARR_INVITATION_SYNC_SECONDS", "60")))
        self.task = None

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        while not self.bridge._closed:
            try:
                await self.sync_once()
            except Exception:
                logger.exception("Failed to synchronize Wizarr invitation identities")
            await asyncio.sleep(self.interval_seconds)

    async def sync_once(self):
        if not self.bridge.wizarr_client:
            return 0
        grants = await self.bridge.db.get_pending_inbox_invitations()
        if not grants:
            return 0
        invitations = await self.bridge.wizarr_client.get_invitations()
        by_code = {invite.get("code"): invite for invite in invitations.get("invitations", [])}
        linked = 0
        for grant in grants:
            invitation = by_code.get(grant["code"])
            email = (invitation or {}).get("used_by")
            if not email:
                continue
            await self.bridge.link_inbox_invitation_identity(grant, email, invitation)
            linked += 1
        if linked:
            logger.info("Linked %s consumed Wizarr invitation(s)", linked)
        return linked

    async def close(self):
        if self.task:
            self.task.cancel()
            self.task = None
