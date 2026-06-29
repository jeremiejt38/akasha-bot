#!/usr/bin/env python3
"""Entrypoint pour le bot.
Charge la config, initialise la base et démarre les services.
"""
import os
from dotenv import load_dotenv
from discord_bot import DiscordBridge

load_dotenv()


def main():
    discord = DiscordBridge()
    # Démarrage synchrone : run() bloque et gère la loop
    discord.run(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    main()
