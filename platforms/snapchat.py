# platforms/snapchat.py
"""
Snapchat stub — very much best-effort; there is no official public API for direct messaging automation.
"""
class SnapchatPlatform:
    def __init__(self, discord, db):
        self.discord = discord
        self.db = db

    async def send(self, platform_user_id: str, text: str):
        print(f"[SNAPCHAT] send to {platform_user_id}: {text}")
