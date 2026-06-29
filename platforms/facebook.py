"""platforms/facebook.py
Stub pour Facebook Messenger.
"""

def start(discord_bridge):
    raise NotImplementedError("Facebook Messenger bridge not implemented")
# platforms/facebook.py
"""
Facebook Messenger stub — best-effort. Implement with facebook-chat-api, fbchat or graph API if available.
"""
class FacebookPlatform:
    def __init__(self, discord, db):
        self.discord = discord
        self.db = db

    async def send(self, platform_user_id: str, text: str):
        print(f"[FACEBOOK] send to {platform_user_id}: {text}")
