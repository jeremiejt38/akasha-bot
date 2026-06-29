# platforms/whatsapp.py
"""
Stub for WhatsApp integration.
Recommended approach: run a whatsapp-web.js service in a separate Node container and communicate via HTTP / websocket
"""
class WhatsAppPlatform:
    def __init__(self, discord, db):
        self.discord = discord
        self.db = db

    async def send(self, platform_user_id: str, text: str):
        # Implement sending messages to WhatsApp (via a node bridge or other library)
        print(f"[WHATSAPP] send to {platform_user_id}: {text}")
