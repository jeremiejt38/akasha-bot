"""platforms/whatsapp.py
Stub pour WhatsApp. Recommandation: exécuter whatsapp-web.js dans un service Docker séparé
et communiquer via IPC (HTTP local / websocket / redis) ou queue.
"""

def start(discord_bridge):
    """Démarrer l'interop WhatsApp (stub).
    Implementation recommended: separate nodejs service that posts to a local HTTP endpoint.
    """
    raise NotImplementedError("WhatsApp bridge not implemented; run whatsapp-web.js in a separate container")
