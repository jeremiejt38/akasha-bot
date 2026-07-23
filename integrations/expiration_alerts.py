"""Automatic expiration alerts for Akasha subscribers.

Runs a daily background task that:
- Notifies the admin about memberships expiring within a configured number of days.
- Notifies the admin about memberships that have already expired.
- Optionally notifies affected subscribers directly.
"""
import os
import asyncio
import datetime
import logging
import discord

logger = logging.getLogger(__name__)

DEFAULT_WARNING_DAYS = int(os.getenv("EXPIRATION_WARNING_DAYS", "7"))
DEFAULT_ALERT_HOUR = int(os.getenv("EXPIRATION_ALERT_HOUR", "9"))
NOTIFY_SUBSCRIBERS = os.getenv("EXPIRATION_NOTIFY_SUBSCRIBERS", "true").lower() in ("1", "true", "yes")
REVOKE_ROLE_ON_EXPIRATION = os.getenv("REVOKE_ROLE_ON_EXPIRATION", "true").lower() in ("1", "true", "yes")
MEMBER_ROLE_NAME = os.getenv("MEMBER_ROLE_NAME", "Abonné")


class ExpirationAlerts:
    """Daily background task for subscription expiration notifications."""

    def __init__(self, discord_bridge, db, guild_id: int, admin_id: int):
        self.discord_bridge = discord_bridge
        self.db = db
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.warning_days = DEFAULT_WARNING_DAYS
        self.alert_hour = DEFAULT_ALERT_HOUR
        self._task = None
        self._stopped = False

    def start(self):
        if self._task is not None:
            return
        self._stopped = False
        self._task = asyncio.create_task(self._loop())
        logger.info("Started expiration alert task")

    def stop(self):
        self._stopped = True
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("Stopped expiration alert task")

    async def _loop(self):
        while not self._stopped:
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                target = now.replace(hour=self.alert_hour, minute=0, second=0, microsecond=0)
                if target <= now:
                    target += datetime.timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.debug("Next expiration alert in %s seconds", wait_seconds)
                await asyncio.sleep(wait_seconds)
                await self._run_check()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Expiration alert loop failed")
                await asyncio.sleep(3600)

    def _parse_date(self, date_str: str | None) -> datetime.datetime | None:
        if not date_str:
            return None
        try:
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            return None

    async def _run_check(self):
        users = await self.db.get_all_users()
        now = datetime.datetime.now(datetime.timezone.utc)

        expiring_soon = []
        already_expired = []

        for user in users:
            expires = self._parse_date(user.get("wizarr_invite_expires"))
            if not expires:
                continue
            days = (expires - now).days
            if days < 0:
                already_expired.append((user, days))
            elif days <= self.warning_days:
                expiring_soon.append((user, days))

        if expiring_soon or already_expired:
            await self._notify_admin(expiring_soon, already_expired)

        if NOTIFY_SUBSCRIBERS:
            for user, days in expiring_soon:
                await self._notify_subscriber(user, days, expired=False)
            for user, days in already_expired:
                await self._notify_subscriber(user, days, expired=True)

        if REVOKE_ROLE_ON_EXPIRATION:
            for user, _days in already_expired:
                await self._revoke_role(user)

    async def _notify_admin(self, expiring_soon: list, already_expired: list):
        try:
            admin = await self.discord_bridge.bot.fetch_user(self.admin_id)
            if admin is None:
                return

            lines = [f"**Alertes d'expiration Akasha** — {datetime.datetime.now(datetime.timezone.utc).strftime('%d/%m/%Y')}"]

            if expiring_soon:
                lines.append(f"\n⏳ Expirant dans ≤ {self.warning_days} jours ({len(expiring_soon)}) :")
                for user, days in expiring_soon:
                    lines.append(
                        f"• <@{user.get('discord_id')}> — {user.get('email') or 'email inconnu'} "
                        f"— expire dans {days} jours ({self._format_date(user.get('wizarr_invite_expires'))})"
                    )

            if already_expired:
                lines.append(f"\n🔴 Expirés ({len(already_expired)}) :")
                for user, days in already_expired:
                    lines.append(
                        f"• <@{user.get('discord_id')}> — {user.get('email') or 'email inconnu'} "
                        f"— expiré depuis {-days} jours ({self._format_date(user.get('wizarr_invite_expires'))})"
                    )

            message = "\n".join(lines)
            if len(message) > 1900:
                message = message[:1900] + "\n... (message tronqué)"
            await admin.send(message)
            logger.info("Sent expiration alert to admin: %s expiring soon, %s expired", len(expiring_soon), len(already_expired))
        except discord.Forbidden:
            logger.warning("Cannot send expiration alert to admin via DM")
        except Exception:
            logger.exception("Failed to send expiration alert to admin")

    async def _notify_subscriber(self, user: dict, days: int, expired: bool):
        try:
            discord_id = user.get("discord_id")
            if not discord_id:
                return
            member_id = int(discord_id)
            if expired:
                text = (
                    "Ton abonnement Akasha a expiré. "
                    "Contacte l'admin sur Discord pour renouveler ton accès."
                )
            else:
                text = (
                    f"Ton abonnement Akasha expire dans {days} jours. "
                    "Contacte l'admin sur Discord si tu souhaites le renouveler."
                )
            user_obj = await self.discord_bridge.bot.fetch_user(member_id)
            if user_obj:
                await user_obj.send(text)
        except discord.Forbidden:
            logger.warning("Cannot notify subscriber %s about expiration", user.get("discord_id"))
        except Exception:
            logger.exception("Failed to notify subscriber %s about expiration", user.get("discord_id"))

    async def _revoke_role(self, user: dict):
        try:
            guild = self.discord_bridge.bot.get_guild(self.guild_id)
            if guild is None:
                guild = await self.discord_bridge.bot.fetch_guild(self.guild_id)
            role = discord.utils.get(guild.roles, name=MEMBER_ROLE_NAME)
            if role is None:
                logger.warning("Member role %s not found for revocation", MEMBER_ROLE_NAME)
                return

            discord_id = user.get("discord_id")
            if not discord_id:
                return
            member = guild.get_member(int(discord_id))
            if member is None:
                try:
                    member = await guild.fetch_member(int(discord_id))
                except Exception:
                    return
            if role in member.roles:
                await member.remove_roles(role, reason="Abonnement expiré")
                logger.info("Revoked member role for user %s", discord_id)
        except Exception:
            logger.exception("Failed to revoke role for user %s", user.get("discord_id"))

    def _format_date(self, date_str: str | None) -> str:
        if not date_str:
            return "date inconnue"
        try:
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return date_str
