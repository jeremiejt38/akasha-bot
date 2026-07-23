"""User synchronization service between Discord, local DB and Overseerr."""
import datetime
import logging
from integrations.onboarding import OnboardingConfig

logger = logging.getLogger(__name__)


class SyncService:
    """Syncs local user data with Overseerr and Discord roles."""

    def __init__(self, discord_bridge, overseerr_client, db):
        self.discord_bridge = discord_bridge
        self.overseerr_client = overseerr_client
        self.db = db
        self.onboarding_config = OnboardingConfig()

    async def sync_all(self, guild) -> dict:
        """Sync all known users with Overseerr and return a summary."""
        if not self.overseerr_client:
            return {"ok": False, "error": "Overseerr not configured", "success": 0, "failed": 0}

        users = await self.db.get_all_users()
        success = 0
        failed = 0
        errors = []

        for user in users:
            member = guild.get_member(int(user["discord_id"]))
            if member is None:
                try:
                    member = await guild.fetch_member(int(user["discord_id"]))
                except Exception:
                    failed += 1
                    continue
            result = await self.sync_user(member)
            if result["ok"]:
                success += 1
            else:
                failed += 1
                errors.append(f"{user.get('discord_id')}: {result['error']}")

        return {"ok": True, "success": success, "failed": failed, "errors": errors}

    async def sync_user(self, member) -> dict:
        """Sync a single Discord member with Overseerr and the local DB.

        Returns a dict with status info.
        """
        if not self.overseerr_client:
            return {"ok": False, "error": "Overseerr not configured"}

        discord_id = str(member.id)
        user = await self.db.get_user_by_discord_id(discord_id)
        email = user.get("email") if user else None

        try:
            if email:
                overseerr_user = await self.overseerr_client.find_user_by_email(email)
            else:
                # Try to find by Discord ID in notification settings
                overseerr_user = await self._find_user_by_discord_id(discord_id)

            if not overseerr_user:
                return {"ok": False, "error": "User not found in Overseerr"}

            overseerr_id = overseerr_user.get("id")
            plex_username = overseerr_user.get("plexUsername")
            email = overseerr_user.get("email", "").lower().strip() if not email else email

            now = datetime.datetime.utcnow().isoformat()

            # Ensure Discord ID is synced to Overseerr
            try:
                await self.overseerr_client.update_user_discord_id(overseerr_id, discord_id)
            except Exception:
                logger.exception("Failed to update Discord ID in Overseerr for %s", discord_id)

            user_fields = {
                "email": email,
                "discord_username": member.name,
                "overseerr_id": overseerr_id,
                "overseerr_username": overseerr_user.get("username") or overseerr_user.get("displayName"),
                "overseerr_plex_username": plex_username,
                "overseerr_discord_ids": discord_id,
                "updated_at": now,
            }
            if user:
                await self.db.update_user(discord_id, **user_fields)
            else:
                await self.db.set_user(
                    discord_id=discord_id,
                    created_at=now,
                    access_type="subscriber",
                    **user_fields,
                )

            current_user = await self.db.get_user_by_discord_id(discord_id)
            role_assigned = await self.discord_bridge.onboarding.apply_access(member, current_user)
            return {"ok": True, "role_assigned": role_assigned}
        except Exception:
            logger.exception("Failed to sync user %s", discord_id)
            return {"ok": False, "error": "Exception during sync"}

    async def _find_user_by_discord_id(self, discord_id: str):
        try:
            return await self.overseerr_client.find_user_by_discord_id(discord_id)
        except Exception:
            logger.exception("Failed to search Overseerr by Discord ID %s", discord_id)
        return None
