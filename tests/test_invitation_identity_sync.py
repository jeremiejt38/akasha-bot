import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.invitation_identity_sync import InvitationIdentitySync


class FakeDatabase:
    async def get_pending_inbox_invitations(self):
        return [
            {"code": "USED", "platform": "TL", "platform_user_id": "1", "channel_id": "10"},
            {"code": "UNUSED", "platform": "WA", "platform_user_id": "2", "channel_id": "11"},
        ]


class FakeWizarr:
    async def get_invitations(self):
        return {"invitations": [{"code": "USED", "used_by": "member@example.com"}, {"code": "UNUSED"}]}


class FakeBridge:
    _closed = False

    def __init__(self):
        self.db = FakeDatabase()
        self.wizarr_client = FakeWizarr()
        self.links = []

    async def link_inbox_invitation_identity(self, grant, email, invitation):
        self.links.append((grant["code"], email, invitation["code"]))


def test_sync_links_only_consumed_invitations():
    bridge = FakeBridge()

    async def run():
        linked = await InvitationIdentitySync(bridge).sync_once()
        assert linked == 1

    import asyncio
    asyncio.run(run())

    assert bridge.links == [("USED", "member@example.com", "USED")]


def test_sync_skips_when_wizarr_is_unconfigured():
    bridge = FakeBridge()
    bridge.wizarr_client = None

    async def run():
        assert await InvitationIdentitySync(bridge).sync_once() == 0

    import asyncio
    asyncio.run(run())
