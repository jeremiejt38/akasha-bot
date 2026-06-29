"""platforms/whatsapp.py
Stub pour WhatsApp. Recommandation: exécuter whatsapp-web.js dans un service Docker séparé
et communiquer via IPC (HTTP local / websocket / redis) ou queue.
"""

def start(discord_bridge):
    """Démarrer l'interop WhatsApp (stub).
    Implementation recommended: separate nodejs service that posts to a local HTTP endpoint.
    """
    raise NotImplementedError("WhatsApp bridge not implemented; run whatsapp-web.js in a separate container")
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
