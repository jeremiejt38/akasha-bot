#!/bin/sh
# Lando wrapper: keep the container alive when env is not configured yet,
# otherwise run the Discord bot.
if [ -z "$DISCORD_TOKEN" ]; then
  echo "DISCORD_TOKEN is missing; container is idling."
  echo "Fill .env and run 'lando restart' to start the bot."
  tail -f /dev/null
fi
exec python main.py
