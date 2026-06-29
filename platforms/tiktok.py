# platforms/tiktok.py
"""
TikTok DM stub — best-effort. Official APIs may not allow DM sending.
"""
class TikTokPlatform:
    def __init__(self, discord, db):
        self.discord = discord
        self.db = db

    async def send(self, platform_user_id: str, text: str):
        print(f"[TIKTOK] send to {platform_user_id}: {text}")
