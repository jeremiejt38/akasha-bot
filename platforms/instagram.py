# platforms/instagram.py
"""
Instagram DM stub — best-effort. Implement using an appropriate library or reverse-engineered approach.
"""
class InstagramPlatform:
    def __init__(self, discord, db):
        self.discord = discord
        self.db = db

    async def send(self, platform_user_id: str, text: str):
        print(f"[INSTAGRAM] send to {platform_user_id}: {text}")
