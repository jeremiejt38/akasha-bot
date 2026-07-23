# discord_bot.py
"""
Discord bot that manages the INBOX category and channels mapping.
Listens for admin replies in the per-user channels and forwards them to the registered platform handlers.

This version supports streaming large attachments to temporary files to avoid using too much memory,
and attempts emoji-based channel prefixes with a safe ASCII fallback.
"""
import asyncio
import datetime
import json
import logging
import io
import csv
import os
import re
import tempfile
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from integrations.auto_responder import AutoResponder
from integrations.health_checker import HealthChecker, CONNECTION_CHECK_MARKER
from integrations.onboarding import OnboardingFlow
from integrations.admin_dashboard import AdminDashboard
from integrations.expiration_alerts import ExpirationAlerts
from integrations.sync_service import SyncService
from integrations.invitation_manager import InvitationManager

INBOX_CATEGORY_NAME = os.getenv("INBOX_CATEGORY_NAME", "📥 INBOX")
BOT_NAME = os.getenv("BOT_NAME", "Akasha")


class RequestConfirmView(discord.ui.View):
    def __init__(self, discord_bridge, overseerr_user_id: int, media_type: str, media_id: int, title: str):
        super().__init__(timeout=60)
        self.discord_bridge = discord_bridge
        self.overseerr_user_id = overseerr_user_id
        self.media_type = media_type
        self.media_id = media_id
        self.title = title

    @discord.ui.button(label="Confirmer la demande", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self.discord_bridge.overseerr_client:
            await interaction.response.send_message(
                f"La demande de contenu n'est pas configurée. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.discord_bridge.overseerr_client.request_media(
                self.media_type, self.media_id, self.overseerr_user_id
            )
            await interaction.followup.send(
                f"✅ Demande créée pour **{self.title}**. Tu recevras une notification quand elle sera disponible.",
                ephemeral=True,
            )
        except Exception as e:
            logger.exception("Failed to create media request")
            await interaction.followup.send(
                f"❌ Impossible de créer la demande. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

logger = logging.getLogger(__name__)

THRESHOLD_MB = int(os.getenv("MAX_ATTACHMENT_MEMORY_MB", "5"))
THRESHOLD_BYTES = THRESHOLD_MB * 1024 * 1024

MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "2000"))

PLATFORM_CHANNEL_MARKERS = {
    "WA": os.getenv("CHANNEL_MARKER_WA", "🟢"),
    "TL": os.getenv("CHANNEL_MARKER_TL", "🔵"),
    "IG": os.getenv("CHANNEL_MARKER_IG", "🟣"),
    "FB": os.getenv("CHANNEL_MARKER_FB", "🔷"),
    "SC": os.getenv("CHANNEL_MARKER_SC", "🟡"),
    "TK": os.getenv("CHANNEL_MARKER_TK", "🔴"),
    "DC": os.getenv("CHANNEL_MARKER_DC", "🟠"),
}

PLATFORM_ASCII_PREFIXES = {
    "WA": "wa",
    "TL": "tl",
    "IG": "ig",
    "FB": "fb",
    "SC": "sc",
    "TK": "tk",
    "DC": "dc",
}


def _truncate_text_for_discord(text: str, author: str, limit: int = MAX_MESSAGE_LENGTH) -> str:
    content = f"**{author}**: {text}" if text else f"**{author}**"
    if len(content) <= limit:
        return content
    reserve = len(f"**{author}**: ") + 3
    truncated = text[: max(0, limit - reserve)] + "..."
    return f"**{author}**: {truncated}"


class DiscordBridge:
    def __init__(self, db, guild_id: int, admin_id: int, overseerr_client=None, wizarr_client=None, tracearr_client=None):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.db = db
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.platform_handlers = {}
        self.overseerr_client = overseerr_client
        self.wizarr_client = wizarr_client
        self.tracearr_client = tracearr_client
        enable_auto_responder = os.getenv("AUTO_RESPONDER_ENABLED", "true").lower() in ("1", "true", "yes")
        self.auto_responder = AutoResponder() if enable_auto_responder else None
        self.health_checker = HealthChecker()
        self.onboarding = OnboardingFlow(self, overseerr_client, db)
        self.admin_dashboard = AdminDashboard(self, db, overseerr_client)
        self.expiration_alerts = ExpirationAlerts(self, db, guild_id, admin_id)
        self.sync_service = SyncService(self, overseerr_client, db)
        self.invitation_manager = InvitationManager(wizarr_client, db)
        self._ready_event = asyncio.Event()
        self._closed = False
        self._bot_task = None

        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot ready as {self.bot.user}")
            try:
                commands_before = [c.name for c in self.bot.tree.get_commands()]
                logger.info("Commands in tree before sync: %s", commands_before)
                synced = await self.bot.tree.sync(guild=discord.Object(id=self.guild_id))
                logger.info("Synced commands for guild %s: %s", self.guild_id, [c.name for c in synced])
            except Exception:
                logger.exception("Failed to sync slash commands")
            try:
                self.onboarding.register_persistent_views(self.bot)
            except Exception:
                logger.exception("Failed to register persistent onboarding views")
            self._ready_event.set()

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author.id == self.bot.user.id:
                return

            if message.guild is None:
                if message.author.id != self.admin_id:
                    await self._handle_inbound_dm(message)
                return

            if message.guild.id != self.guild_id:
                return

            if message.author.id == self.admin_id:
                channel_id = message.channel.id
                mapping = await self.db.get_mapping_by_channel(channel_id)
                if mapping:
                    platform, platform_user_id = mapping
                    logger.debug("Admin reply in channel %s -> platform=%s user=%s", channel_id, platform, platform_user_id)
                    handler = self.platform_handlers.get(platform)
                    if handler and hasattr(handler, 'send'):
                        attachments = []
                        for att in message.attachments:
                            try:
                                size = getattr(att, 'size', None) or 0
                                if size and size >= THRESHOLD_BYTES:
                                    tmp = tempfile.NamedTemporaryFile(delete=False)
                                    tmp.close()
                                    try:
                                        await att.save(tmp.name)
                                        attachments.append({
                                            'path': tmp.name,
                                            'filename': att.filename,
                                            'content_type': att.content_type,
                                        })
                                    except Exception:
                                        try:
                                            os.unlink(tmp.name)
                                        except Exception:
                                            pass
                                        raise
                                else:
                                    data = await att.read()
                                    attachments.append({
                                        'bytes': data,
                                        'filename': att.filename,
                                        'content_type': att.content_type,
                                    })
                            except Exception:
                                logger.exception(f"Failed to download attachment {getattr(att, 'url', '<unknown>')}")
                        if message.content or attachments:
                            logger.debug("Forwarding admin reply to %s (text=%r, attachments=%s)", platform, message.content[:200], len(attachments))
                            try:
                                await handler.send(platform_user_id, message.content or "", attachments=attachments)
                            except Exception as e:
                                logger.exception(f"Failed to forward admin message to platform {platform}: {e}")
                    else:
                        logger.warning("No send handler for platform %s", platform)
                else:
                    logger.debug("No mapping found for channel %s", channel_id)
                return

        @self.bot.event
        async def on_member_join(member: discord.Member):
            if member.guild.id != self.guild_id or member.bot:
                return
            await self.onboarding.start(member)

        @self.bot.event
        async def on_member_update(before: discord.Member, after: discord.Member):
            if after.guild.id != self.guild_id or after.bot:
                return
            try:
                before_completed = before.flags.completed_onboarding if before.flags else False
                after_completed = after.flags.completed_onboarding if after.flags else False
            except AttributeError:
                return
            if not before_completed and after_completed:
                await self.onboarding.start(after)

        whatsapp_cmd = app_commands.Command(
            name="whatsapp",
            description="Regenerate WhatsApp QR code and send it via DM",
            callback=self._whatsapp_command
        )
        self.bot.tree.add_command(whatsapp_cmd, guild=discord.Object(id=self.guild_id))

        link_cmd = app_commands.Command(
            name="link",
            description="Lie ton compte Discord à ton compte Overseerr avec ton email",
            callback=self._link_command
        )
        self.bot.tree.add_command(link_cmd, guild=discord.Object(id=self.guild_id))

        invite_cmd = app_commands.Command(
            name="invite",
            description="Créer une invitation Wizarr et l'envoyer à l'utilisateur de cet INBOX (admin only)",
            callback=self._invite_command
        )
        self.bot.tree.add_command(invite_cmd, guild=discord.Object(id=self.guild_id))

        account_cmd = app_commands.Command(
            name="account",
            description="Affiche les informations de ton compte Akasha",
            callback=self._account_command
        )
        self.bot.tree.add_command(account_cmd, guild=discord.Object(id=self.guild_id))

        request_cmd = app_commands.Command(
            name="request",
            description="Demande un film ou une série sur Akasha",
            callback=self._request_command
        )
        self.bot.tree.add_command(request_cmd, guild=discord.Object(id=self.guild_id))

        status_cmd = app_commands.Command(
            name="status",
            description="Affiche l'état des services Akasha",
            callback=self._status_command
        )
        self.bot.tree.add_command(status_cmd, guild=discord.Object(id=self.guild_id))

        dashboard_cmd = app_commands.Command(
            name="dashboard",
            description="Ouvre le tableau de bord admin interactif (admin only)",
            callback=self._dashboard_command
        )
        self.bot.tree.add_command(dashboard_cmd, guild=discord.Object(id=self.guild_id))

        reload_cmd = app_commands.Command(
            name="reload",
            description="Recharge la configuration de l'auto-responder (admin only)",
            callback=self._reload_command
        )
        self.bot.tree.add_command(reload_cmd, guild=discord.Object(id=self.guild_id))

        note_cmd = app_commands.Command(
            name="note",
            description="Ajoute une note privée sur un abonné (admin only)",
            callback=self._note_command
        )
        note_cmd = app_commands.describe(
            membre="L'abonné ciblé",
            texte="La note à enregistrer"
        )(note_cmd)
        self.bot.tree.add_command(note_cmd, guild=discord.Object(id=self.guild_id))

        sync_cmd = app_commands.Command(
            name="sync",
            description="Synchronise un abonné avec Overseerr (admin only)",
            callback=self._sync_command
        )
        sync_cmd = app_commands.describe(
            membre="L'abonné à synchroniser (laisse vide pour tous)"
        )(sync_cmd)
        self.bot.tree.add_command(sync_cmd, guild=discord.Object(id=self.guild_id))

        renew_cmd = app_commands.Command(
            name="renew",
            description="Demander le renouvellement de ton abonnement Akasha",
            callback=self._renew_command
        )
        self.bot.tree.add_command(renew_cmd, guild=discord.Object(id=self.guild_id))

        export_cmd = app_commands.Command(
            name="export",
            description="Exporte la liste des abonnés au format CSV (admin only)",
            callback=self._export_command
        )
        self.bot.tree.add_command(export_cmd, guild=discord.Object(id=self.guild_id))

        support_cmd = app_commands.Command(
            name="support",
            description="Ouvre un ticket support auprès de l'équipe Akasha",
            callback=self._support_command
        )
        support_cmd = app_commands.describe(
            sujet="Le sujet de ta demande",
            description="Décris ton problème ou ta question"
        )(support_cmd)
        self.bot.tree.add_command(support_cmd, guild=discord.Object(id=self.guild_id))

        feedback_cmd = app_commands.Command(
            name="feedback",
            description="Envoie un feedback anonyme à l'équipe Akasha",
            callback=self._feedback_command
        )
        feedback_cmd = app_commands.describe(
            message="Ton message de feedback"
        )(feedback_cmd)
        self.bot.tree.add_command(feedback_cmd, guild=discord.Object(id=self.guild_id))

        faq_cmd = app_commands.Command(
            name="faq",
            description="Affiche les questions fréquentes",
            callback=self._faq_command
        )
        self.bot.tree.add_command(faq_cmd, guild=discord.Object(id=self.guild_id))

        invitations_cmd = app_commands.Command(
            name="invitations",
            description="Gère les invitations Wizarr (admin only)",
            callback=self._invitations_command
        )
        invitations_cmd = app_commands.describe(
            statut="Filtrer par statut: all, unused, used, expired"
        )(invitations_cmd)
        self.bot.tree.add_command(invitations_cmd, guild=discord.Object(id=self.guild_id))

        logs_cmd = app_commands.Command(
            name="logs",
            description="Affiche les dernières actions auditées (admin only)",
            callback=self._logs_command
        )
        logs_cmd = app_commands.describe(
            limite="Nombre d'entrées à afficher (défaut 20, max 100)"
        )(logs_cmd)
        self.bot.tree.add_command(logs_cmd, guild=discord.Object(id=self.guild_id))

    async def _handle_inbound_dm(self, message: discord.Message):
        try:
            user_id = str(message.author.id)
            display_name = message.author.display_name or message.author.name or user_id
            logger.debug("Discord DM received from user %s", user_id)

            attachments = []
            for att in message.attachments:
                try:
                    size = getattr(att, "size", None) or 0
                    if size and size >= THRESHOLD_BYTES:
                        tmp = tempfile.NamedTemporaryFile(delete=False)
                        tmp.close()
                        try:
                            await att.save(tmp.name)
                            attachments.append({
                                "path": tmp.name,
                                "filename": att.filename,
                                "content_type": att.content_type,
                            })
                        except Exception:
                            try:
                                os.unlink(tmp.name)
                            except Exception:
                                pass
                            raise
                    else:
                        data = await att.read()
                        attachments.append({
                            "bytes": data,
                            "filename": att.filename,
                            "content_type": att.content_type,
                        })
                except Exception:
                    logger.exception("Failed to download Discord DM attachment from user %s", user_id)

            await self.post_inbound_message(
                "DC", user_id, display_name, message.content or "", attachments=attachments
            )
        except Exception:
            logger.exception("Failed to handle Discord DM from user %s", message.author.id)

    async def _whatsapp_command(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            if interaction.response.is_done():
                await interaction.followup.send("Only the admin can use this command.", ephemeral=True)
            else:
                await interaction.response.send_message("Only the admin can use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        base_url = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{base_url}/restart", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status >= 400:
                        await interaction.followup.send(f"{BOT_NAME} n'a pas réussi à redémarrer le pont WhatsApp.", ephemeral=True)
                        return

                qr_text = None
                for _ in range(15):
                    await asyncio.sleep(2)
                    async with session.get(f"{base_url}/qr", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            qr_text = data.get("qr_text")
                            if qr_text:
                                break

            if not qr_text:
                await interaction.followup.send("Aucun QR code n'a été généré. WhatsApp est peut-être déjà connecté.", ephemeral=True)
                return

            try:
                await interaction.user.send(f"Scan this QR code with WhatsApp to authenticate:\n```\n{qr_text}\n```")
                await interaction.followup.send("QR code envoyé en DM.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("Je ne peux pas t'envoyer de DM. Active les messages directs.", ephemeral=True)
        except Exception as e:
            logger.exception("WhatsApp command failed")
            await interaction.followup.send(f"Erreur {BOT_NAME} : {e}", ephemeral=True)

    async def _link_command(self, interaction: discord.Interaction, email: str):
        if not self.overseerr_client:
            await interaction.response.send_message(f"La liaison de compte n'est pas configurée. Contacte l'équipe {BOT_NAME}.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        email_clean = email.lower().strip()
        requester_discord_id = str(interaction.user.id)

        try:
            overseerr_user = await self.overseerr_client.find_user_by_email(email_clean)
            if not overseerr_user:
                await interaction.followup.send(
                    "Aucun compte actif trouvé avec cette adresse email.", ephemeral=True
                )
                return

            overseerr_id = overseerr_user.get("id")
            existing_discord_ids = await self.overseerr_client.get_user_discord_ids(overseerr_id)
            existing_ids_str = [str(d) for d in existing_discord_ids]

            if requester_discord_id in existing_ids_str:
                await interaction.followup.send(
                    "Ton compte Discord est déjà lié à ce compte Overseerr.", ephemeral=True
                )
                return

            if existing_discord_ids:
                await interaction.followup.send(
                    "Ce compte email est déjà lié à un autre compte Discord.", ephemeral=True
                )
                return

            await self.overseerr_client.update_user_discord_id(overseerr_id, requester_discord_id)

            # Sync Wizarr invitation info
            wizarr_invite_code = None
            wizarr_invite_expires = None
            if self.wizarr_client:
                wizarr_invite = await self.wizarr_client.find_invitation_by_email(email_clean)
                if wizarr_invite:
                    wizarr_invite_code = wizarr_invite.get("code")
                    wizarr_invite_expires = wizarr_invite.get("expires")

            # Sync Tracearr data
            tracearr_data = None
            plex_username = overseerr_user.get("plexUsername")
            if self.tracearr_client and plex_username:
                tracearr_data = await self.tracearr_client.find_user_by_username(plex_username)

            now = datetime.datetime.utcnow().isoformat()
            existing_user = await self.db.get_user_by_discord_id(requester_discord_id)
            created_at = existing_user.get("created_at") if existing_user else now
            await self.db.set_user(
                discord_id=requester_discord_id,
                email=email_clean,
                discord_username=interaction.user.name,
                overseerr_id=overseerr_id,
                overseerr_username=overseerr_user.get("username") or overseerr_user.get("displayName"),
                overseerr_plex_username=plex_username,
                overseerr_discord_ids=",".join([requester_discord_id] + existing_ids_str),
                wizarr_invite_code=wizarr_invite_code,
                wizarr_invite_expires=wizarr_invite_expires,
                created_at=created_at,
                months_subscribed=existing_user.get("months_subscribed") if existing_user else 0,
                tracearr_user_id=tracearr_data.get("id") if tracearr_data else None,
                tracearr_username=tracearr_data.get("username") if tracearr_data else None,
                tracearr_trust_score=tracearr_data.get("trustScore") if tracearr_data else None,
                tracearr_total_violations=tracearr_data.get("totalViolations") if tracearr_data else None,
                tracearr_session_count=tracearr_data.get("sessionCount") if tracearr_data else None,
                tracearr_last_activity=tracearr_data.get("lastActivityAt") if tracearr_data else None,
                tracearr_stats=json.dumps(tracearr_data) if tracearr_data else None,
                updated_at=now,
            )

            lines = [f"Compte lié avec succès à **{overseerr_user.get('email', email_clean)}** ({overseerr_user.get('displayName') or overseerr_user.get('plexUsername') or 'utilisateur'})."]
            if plex_username:
                lines.append(f"Plex : `{plex_username}`")
            if wizarr_invite_code:
                lines.append(f"Invitation Wizarr : `{wizarr_invite_code}`")
            if tracearr_data:
                lines.append(f"Trust score Tracearr : {tracearr_data.get('trustScore', 'N/A')}")
            await interaction.followup.send("\n".join(lines), ephemeral=True)
        except Exception:
            logger.exception("Link command failed for email=%s discord=%s", email_clean, requester_discord_id)
            await interaction.followup.send(
                f"Une erreur s'est produite pendant la liaison. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    @staticmethod
    def _parse_invite_type(type_str: str) -> tuple[int, bool]:
        """Return (duration_days, is_trial)."""
        type_str = type_str.lower().strip()
        if type_str in ("free", "test", "essai"):
            return int(os.getenv("TRIAL_DURATION_DAYS", "14")), True
        match = re.match(r"^(\d+)([jsma])$", type_str)
        if not match:
            raise ValueError("Type invalide. Utilise 'free', 'test', 'essai' ou <nombre><j|s|m|a>.")
        amount = int(match.group(1))
        multipliers = {"j": 1, "s": 7, "m": 30, "a": 365}
        return amount * multipliers[match.group(2)], False

    async def _invite_command(self, interaction: discord.Interaction, type: str):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return

        if not self.wizarr_client:
            await interaction.response.send_message(f"L'intégration Wizarr n'est pas configurée. Contacte l'équipe {BOT_NAME}.", ephemeral=True)
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or channel.category.name != INBOX_CATEGORY_NAME:
            await interaction.response.send_message("Cette commande ne peut être utilisée que dans un canal INBOX.", ephemeral=True)
            return

        mapping = await self.db.get_mapping_by_channel(channel.id)
        if not mapping:
            await interaction.response.send_message("Aucun destinataire lié à ce canal.", ephemeral=True)
            return

        platform, platform_user_id = mapping
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            duration_days, is_trial = self._parse_invite_type(type)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        try:
            # Discord DM stacking: add remaining days from a used non-expired invitation
            if platform == "DC":
                duration_days = await self._compute_stacked_duration_days(platform_user_id, duration_days)

            invite = await self._create_wizarr_invitation(duration_days, is_trial)
            code = invite.get("code")
            base_url = self.wizarr_client.base_url.replace("http://", "https://")
            url = f"{base_url}/j/{code}"

            is_existing = await self._is_existing_user(platform, platform_user_id)
            message = self._build_invite_message(is_trial, is_existing, code, url, duration_days)

            # Forward the invite message to the recipient platform
            handler = self.platform_handlers.get(platform)
            if not handler:
                await interaction.followup.send(f"Aucun handler pour la plateforme {platform}.", ephemeral=True)
                return
            await handler.send(platform_user_id, message)

            # Store the invitation for Discord users so stacking works next time
            if platform == "DC":
                user = await self.db.get_user_by_discord_id(platform_user_id)
                months = (user.get("months_subscribed") or 0) + max(1, int(duration_days / 30))
                await self.db.update_user(
                    platform_user_id,
                    wizarr_invite_code=code,
                    wizarr_invite_expires=invite.get("expires"),
                    months_subscribed=months,
                    updated_at=datetime.datetime.utcnow().isoformat(),
                )

            await interaction.followup.send(
                f"Invitation `{code}` créée ({duration_days} jours) et envoyée à {platform}.", ephemeral=True
            )

            try:
                await self.db.log_audit(
                    action="invite_created",
                    admin_id=str(interaction.user.id),
                    discord_id=platform_user_id if platform == "DC" else None,
                    details=f"code={code}, duration={duration_days}, platform={platform}",
                )
            except Exception:
                logger.exception("Failed to log invite creation")
        except Exception:
            logger.exception("Invite command failed in channel %s", channel.id)
            await interaction.followup.send(f"Une erreur s'est produite en créant l'invitation. Contacte l'équipe {BOT_NAME}.", ephemeral=True)

    async def _compute_stacked_duration_days(self, discord_id: str, requested_days: int) -> int:
        user = await self.db.get_user_by_discord_id(discord_id)
        if not user:
            return requested_days
        code = user.get("wizarr_invite_code")
        if not code:
            return requested_days
        try:
            inv = await self.wizarr_client.get_invitation_by_code(code)
            if not inv or inv.get("status") != "used":
                return requested_days
            expires = inv.get("expires")
            if not expires:
                return requested_days
            expires_dt = datetime.datetime.fromisoformat(expires.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            remaining = (expires_dt - now).total_seconds() / 86400
            if remaining > 0:
                return requested_days + int(remaining)
        except Exception:
            logger.exception("Failed to compute stacked duration for discord_id=%s", discord_id)
        return requested_days

    async def _is_existing_user(self, platform: str, platform_user_id: str) -> bool:
        if platform != "DC" or not self.wizarr_client:
            return False
        user = await self.db.get_user_by_discord_id(platform_user_id)
        if not user or not user.get("email"):
            return False
        wizarr_user = await self.wizarr_client.find_user_by_email(user["email"])
        return bool(wizarr_user)

    async def _create_wizarr_invitation(self, duration_days: int, is_trial: bool):
        server_ids = [int(s) for s in os.getenv("WIZARR_INVITE_SERVER_IDS", "1,2").split(",") if s.strip()]
        if is_trial:
            expires_in_days = duration_days
        else:
            expires_in_days = int(os.getenv("WIZARR_INVITE_EXPIRES_DAYS", "7"))
        return await self.wizarr_client.create_invitation(
            server_ids=server_ids,
            duration=str(duration_days),
            expires_in_days=expires_in_days,
            unlimited=False,
            allow_downloads=True,
            allow_live_tv=True,
            allow_mobile_uploads=True,
        )

    @staticmethod
    def _build_invite_message(is_trial: bool, is_existing: bool, code: str, url: str, duration_days: int) -> str:
        akasha_url = os.getenv("AKASHA_INVITE_URL", "https://akasha.ing")
        if is_trial:
            return (
                f"Bienvenue sur Akasha ton essaie de 2 semaines a commencé, pour rejoindre Akasha rend toi sur "
                f"{akasha_url} clique le bouton \"Frappez aux portes\" tout en bas et entrez le code d'invitation suivant : {code}\n\n"
                f"Ou tu peux utiliser le lien direct : {url}\n\n"
                f"Une fois ton essais terminé contacte moi a nouveau si tu souhaite souscrire un Abonnement."
            )
        if is_existing:
            return f"Pour valider le renouvellement de ton compte clique sur le lien suivant et assure toi de te connecter au bon compte Plex : {url}"
        return (
            f"Bienvenue ! Pour valider ton inscription à Akasha rend toi sur {akasha_url} clique le bouton "
            f"\"Frappez aux portes\" tout en bas et entrez le code d'invitation suivant : {code}\n\n"
            f"Ou tu peux utiliser le lien direct : {url}"
        )

    async def _account_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        discord_id = str(interaction.user.id)
        user = await self.db.get_user_by_discord_id(discord_id)

        if not user or not user.get("overseerr_id"):
            await interaction.followup.send(
                f"Ton compte n'est pas encore lié. Utilise `/link <email>` pour le lier.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Ton compte {BOT_NAME}",
            color=discord.Color.blue(),
        )

        if user.get("email"):
            embed.add_field(name="Email", value=user["email"], inline=True)
        if user.get("overseerr_username"):
            embed.add_field(name="Utilisateur Seerr", value=user["overseerr_username"], inline=True)
        if user.get("overseerr_plex_username"):
            embed.add_field(name="Plex", value=user["overseerr_plex_username"], inline=True)

        invite_expires = user.get("wizarr_invite_expires")
        if invite_expires:
            expires_dt = datetime.datetime.fromisoformat(invite_expires.replace("Z", "+00:00"))
            embed.add_field(name="Expiration", value=expires_dt.strftime("%d/%m/%Y"), inline=True)
        else:
            embed.add_field(name="Expiration", value="Inconnue", inline=True)

        if user.get("tracearr_trust_score") is not None:
            embed.add_field(name="Trust score", value=str(user["tracearr_trust_score"]), inline=True)

        renewal_status = user.get("renewal_status")
        if renewal_status == "pending":
            embed.add_field(name="Renouvellement", value="Demande en attente", inline=True)

        links = []
        if os.getenv("PLEX_URL"):
            links.append(f"[Plex]({os.getenv('PLEX_URL')})")
        if os.getenv("JELLYFIN_URL"):
            links.append(f"[Jellyfin]({os.getenv('JELLYFIN_URL')})")
        if os.getenv("OVERSEERR_BASE_URL"):
            links.append(f"[Seerr]({os.getenv('OVERSEERR_BASE_URL')})")
        if links:
            embed.add_field(name="Liens utiles", value=" · ".join(links), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _request_command(self, interaction: discord.Interaction, titre: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        discord_id = str(interaction.user.id)
        user = await self.db.get_user_by_discord_id(discord_id)

        if not user or not user.get("overseerr_id"):
            await interaction.followup.send(
                f"Ton compte n'est pas encore lié. Utilise `/link <email>` pour demander du contenu.", ephemeral=True
            )
            return

        if not self.overseerr_client:
            await interaction.followup.send(
                f"La demande de contenu n'est pas configurée. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )
            return

        try:
            results = await self.overseerr_client.search_media(titre, limit=5)
            items = results.get("results", [])
            if not items:
                await interaction.followup.send(
                    f"Aucun résultat trouvé pour **{titre}**.", ephemeral=True
                )
                return

            # For now, take the first result and ask for confirmation
            first = items[0]
            media_type = first.get("mediaType")  # 'movie' or 'tv'
            tmdb_id = first.get("id")
            title = first.get("title") or first.get("name") or titre
            year = first.get("releaseDate") or first.get("firstAirDate") or "?"

            view = RequestConfirmView(self, user["overseerr_id"], media_type, tmdb_id, title)
            embed = discord.Embed(
                title="Demande de contenu",
                description=f"Voulez-vous demander **{title}** ({year}) ?",
                color=discord.Color.gold(),
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Request command failed for user %s title %s", discord_id, titre)
            await interaction.followup.send(
                f"Une erreur s'est produite pendant la recherche. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _status_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await self.health_checker.check_all()
            formatted = self.health_checker.format_results(results)
            all_ok = all(r.get("ok") for r in results)
            embed = discord.Embed(
                title=f"État des services {BOT_NAME}",
                description=formatted,
                color=discord.Color.green() if all_ok else discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Status command failed")
            await interaction.followup.send(
                f"Impossible de vérifier l'état des services. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _dashboard_command(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return
        await self.admin_dashboard.send_dashboard(interaction)

    async def _reload_command(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return
        if not self.auto_responder:
            await interaction.response.send_message(
                "L'auto-responder n'est pas activé.", ephemeral=True
            )
            return
        try:
            self.auto_responder.reload()
            await interaction.response.send_message(
                "✅ Configuration de l'auto-responder rechargée.", ephemeral=True
            )
        except Exception:
            logger.exception("Failed to reload auto-responder config")
            await interaction.response.send_message(
                "❌ Impossible de recharger l'auto-responder.", ephemeral=True
            )

    async def _note_command(self, interaction: discord.Interaction, membre: discord.Member, texte: str):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return
        await self.db.update_user(
            str(membre.id),
            admin_notes=texte,
            updated_at=datetime.datetime.utcnow().isoformat(),
        )
        await interaction.response.send_message(
            f"✅ Note enregistrée pour <@{membre.id}>.", ephemeral=True
        )

        try:
            await self.db.log_audit(
                action="admin_note",
                admin_id=str(interaction.user.id),
                discord_id=str(membre.id),
                details=texte[:200],
            )
        except Exception:
            logger.exception("Failed to log admin note")

    async def _feedback_command(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        discord_id = str(interaction.user.id)

        try:
            admin = await self.bot.fetch_user(self.admin_id)
            if admin:
                await admin.send(
                    f"💬 **Feedback de <@{discord_id}>**\n{message[:1500]}"
                )
            await interaction.followup.send(
                f"✅ Feedback envoyé. Merci d'aider à améliorer {BOT_NAME} !", ephemeral=True
            )

            try:
                await self.db.log_audit(
                    action="feedback_sent",
                    discord_id=discord_id,
                    details=message[:200],
                )
            except Exception:
                logger.exception("Failed to log feedback")
        except Exception:
            logger.exception("Feedback command failed for user %s", discord_id)
            await interaction.followup.send(
                f"❌ Impossible d'envoyer le feedback. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _faq_command(self, interaction: discord.Interaction):
        if not self.auto_responder:
            await interaction.response.send_message(
                "L'auto-responder n'est pas activé.", ephemeral=True
            )
            return

        questions = self.auto_responder.list_questions(limit=15)
        if not questions:
            await interaction.response.send_message(
                "Aucune question fréquente n'est configurée.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"FAQ {BOT_NAME}",
            description="Voici les questions les plus fréquentes :",
            color=discord.Color.blue(),
        )
        for question, answer in questions:
            # Truncate long answers for embed field values
            value = answer[:1020] + "..." if len(answer) > 1024 else answer
            embed.add_field(name=f"Q: {question}", value=f"R: {value}", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _logs_command(self, interaction: discord.Interaction, limite: int = 20):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return

        limite = max(1, min(limite, 100))
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            logs = await self.db.get_recent_audit_logs(limit=limite)
            if not logs:
                await interaction.followup.send("Aucune entrée d'audit trouvée.", ephemeral=True)
                return

            lines = []
            for log in logs:
                created = log.get("created_at", "?")
                try:
                    dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created = dt.strftime("%d/%m %H:%M")
                except Exception:
                    pass
                action = log.get("action", "?")
                discord_id = log.get("discord_id")
                admin_id = log.get("admin_id")
                details = log.get("details") or ""
                user_str = f" user=<@{discord_id}>" if discord_id else ""
                admin_str = f" admin=<@{admin_id}>" if admin_id else ""
                lines.append(f"`[{created}]` **{action}**{user_str}{admin_str} {details}")

            message = "\n".join(lines)
            if len(message) > 1900:
                message = message[:1900] + "\n... (tronqué)"

            embed = discord.Embed(
                title=f"Dernières actions auditées ({len(logs)})",
                description=message,
                color=discord.Color.dark_grey(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Logs command failed")
            await interaction.followup.send(
                f"❌ Impossible de récupérer les logs. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _invitations_command(self, interaction: discord.Interaction, statut: str = "all"):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return
        if not self.wizarr_client:
            await interaction.response.send_message(
                "La gestion des invitations n'est pas configurée.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            invitations = await self.invitation_manager.list_invitations(
                status=statut if statut != "all" else None
            )
            if not invitations:
                await interaction.followup.send(
                    f"Aucune invitation trouvée avec le statut `{statut}`.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"Invitations Wizarr — {statut}",
                description=f"{len(invitations)} invitation(s) trouvée(s). Clique sur un bouton pour révoquer.",
                color=discord.Color.purple(),
            )
            for inv in invitations[:10]:
                embed.add_field(
                    name=f"`{inv.get('code')}` — {inv.get('status')}",
                    value=self.invitation_manager.format_invitation(inv),
                    inline=False,
                )

            view = InvitationsView(self.invitation_manager, invitations[:10])
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Invitations command failed")
            await interaction.followup.send(
                f"❌ Impossible de récupérer les invitations. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _support_command(self, interaction: discord.Interaction, sujet: str, description: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        discord_id = str(interaction.user.id)
        user = await self.db.get_user_by_discord_id(discord_id)

        if not user or not user.get("overseerr_id"):
            await interaction.followup.send(
                f"Ton compte n'est pas lié. Utilise `/link <email>` pour le lier.", ephemeral=True
            )
            return

        try:
            admin = await self.bot.fetch_user(self.admin_id)
            if admin:
                await admin.send(
                    f"🎫 **Ticket support de <@{discord_id}>** ({user.get('email') or 'email inconnu'})\n"
                    f"**Sujet :** {sujet}\n"
                    f"**Description :** {description[:1500]}"
                )
            await interaction.followup.send(
                f"✅ Ticket envoyé. L'équipe {BOT_NAME} te répondra dès que possible.", ephemeral=True
            )
        except Exception:
            logger.exception("Support command failed for user %s", discord_id)
            await interaction.followup.send(
                f"❌ Impossible d'envoyer le ticket. Contacte l'équipe {BOT_NAME} directement.", ephemeral=True
            )

    async def _export_command(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            users = await self.db.get_all_users()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "discord_id", "discord_username", "email", "overseerr_username",
                "plex_username", "created_at", "expires_at", "months_subscribed",
                "trust_score", "admin_notes", "renewal_status",
            ])
            for u in users:
                writer.writerow([
                    u.get("discord_id"),
                    u.get("discord_username"),
                    u.get("email"),
                    u.get("overseerr_username"),
                    u.get("overseerr_plex_username"),
                    u.get("created_at"),
                    u.get("wizarr_invite_expires"),
                    u.get("months_subscribed") or 0,
                    u.get("tracearr_trust_score") or "",
                    u.get("admin_notes") or "",
                    u.get("renewal_status") or "",
                ])

            output.seek(0)
            file = discord.File(io.BytesIO(output.getvalue().encode("utf-8")), filename="akasha_subscribers.csv")
            await interaction.followup.send(
                f"📄 Export de {len(users)} abonnés.", file=file, ephemeral=True
            )
        except Exception:
            logger.exception("Export command failed")
            await interaction.followup.send(
                f"❌ Impossible d'exporter les abonnés. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _renew_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        discord_id = str(interaction.user.id)
        user = await self.db.get_user_by_discord_id(discord_id)

        if not user or not user.get("overseerr_id"):
            await interaction.followup.send(
                f"Ton compte n'est pas lié. Utilise `/link <email>` pour le lier.", ephemeral=True
            )
            return

        try:
            now = datetime.datetime.utcnow().isoformat()
            await self.db.update_user(
                discord_id,
                renewal_requested_at=now,
                renewal_status="pending",
                updated_at=now,
            )

            # Notify admin
            try:
                admin = await self.bot.fetch_user(self.admin_id)
                if admin:
                    await admin.send(
                        f"Demande de renouvellement de <@{discord_id}> ({user.get('email') or 'email inconnu'}).\n"
                        f"Utilise `/dashboard` pour voir les détails."
                    )
            except Exception:
                logger.exception("Failed to notify admin about renewal request from %s", discord_id)

            await interaction.followup.send(
                f"✅ Demande de renouvellement envoyée. L'équipe {BOT_NAME} te contactera bientôt.", ephemeral=True
            )

            try:
                await self.db.log_audit(
                    action="renew_requested",
                    discord_id=discord_id,
                    details=f"email={user.get('email')}",
                )
            except Exception:
                logger.exception("Failed to log renewal request")
        except Exception:
            logger.exception("Renew command failed for user %s", discord_id)
            await interaction.followup.send(
                f"❌ Impossible d'enregistrer la demande. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _sync_command(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Seul l'admin peut utiliser cette commande.", ephemeral=True)
            return
        if not self.overseerr_client:
            await interaction.response.send_message(
                "La synchronisation Overseerr n'est pas configurée.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            guild = self.bot.get_guild(self.guild_id) or await self.bot.fetch_guild(self.guild_id)
            if membre:
                result = await self.sync_service.sync_user(membre)
                if result["ok"]:
                    await interaction.followup.send(
                        f"✅ <@{membre.id}> synchronisé avec succès.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ Échec de la synchronisation de <@{membre.id}> : {result['error']}", ephemeral=True
                    )
                return

            users = await self.db.get_all_users()
            success = 0
            failed = 0
            for user in users:
                member = guild.get_member(int(user["discord_id"]))
                if member is None:
                    try:
                        member = await guild.fetch_member(int(user["discord_id"]))
                    except Exception:
                        failed += 1
                        continue
                result = await self.sync_service.sync_user(member)
                if result["ok"]:
                    success += 1
                else:
                    failed += 1

            await interaction.followup.send(
                f"✅ Synchronisation terminée : {success} succès, {failed} échecs.", ephemeral=True
            )

            try:
                target = str(membre.id) if membre else "all"
                await self.db.log_audit(
                    action="sync_manual",
                    admin_id=str(interaction.user.id),
                    discord_id=target if membre else None,
                    details=f"success={success}, failed={failed}",
                )
            except Exception:
                logger.exception("Failed to log sync command")
        except Exception:
            logger.exception("Sync command failed")
            await interaction.followup.send(
                f"❌ Une erreur s'est produite pendant la synchronisation. Contacte l'équipe {BOT_NAME}.", ephemeral=True
            )

    async def _get_user_data_for_inbound(self, platform_tag: str, platform_user_id: str):
        if platform_tag == "DC":
            return await self.db.get_user_by_discord_id(platform_user_id)
        return None

    async def _bump_channel_to_top(self, channel: discord.TextChannel):
        try:
            category = channel.category
            if category is None:
                return
            same_category = [c for c in category.channels if isinstance(c, discord.TextChannel)]
            if not same_category:
                return
            min_pos = min(c.position for c in same_category)
            if channel.position == min_pos:
                return
            await channel.edit(position=min_pos)
            logger.debug("Bumped channel %s to top of category %s", channel.id, category.id)
        except Exception:
            logger.exception("Failed to bump channel %s to top", channel.id)

    async def _send_auto_response(self, platform_tag: str, platform_user_id: str, channel, text: str, user_data: dict) -> bool:
        try:
            response = self.auto_responder.respond(text, user_data)
            if not response:
                return False

            if response == CONNECTION_CHECK_MARKER:
                logger.info("Health check triggered for %s user=%s", platform_tag, platform_user_id)
                results = await self.health_checker.check_all()
                response = self.health_checker.format_results(results)

            logger.info("Auto-responding to %s user=%s with matched answer", platform_tag, platform_user_id)
            handler = self.platform_handlers.get(platform_tag)
            if handler:
                await handler.send(platform_user_id, response)
            await channel.send(f"**Auto-reply**: {response}")
            return True
        except Exception:
            logger.exception("Auto-responder failed for %s user=%s", platform_tag, platform_user_id)
            return False

    async def start(self, token: str):
        loop = asyncio.get_event_loop()
        self._bot_task = loop.create_task(self.bot.start(token))
        await self._ready_event.wait()
        self.expiration_alerts.start()
        self._auto_sync_task = loop.create_task(self._run_auto_sync())

    async def close(self):
        self._closed = True
        self.expiration_alerts.stop()
        if getattr(self, "_auto_sync_task", None):
            self._auto_sync_task.cancel()
        await self.bot.close()

    async def _run_auto_sync(self):
        interval_hours = int(os.getenv("AUTO_SYNC_INTERVAL_HOURS", "24"))
        interval_seconds = max(3600, interval_hours * 3600)
        logger.info("Starting auto-sync job every %s hours", interval_hours)
        while not self._closed:
            try:
                await asyncio.sleep(interval_seconds)
                if self._closed:
                    break
                await self._perform_auto_sync()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Auto-sync job failed")
                await asyncio.sleep(3600)

    async def _perform_auto_sync(self):
        if not self.overseerr_client:
            return
        try:
            guild = self.bot.get_guild(self.guild_id) or await self.bot.fetch_guild(self.guild_id)
            result = await self.sync_service.sync_all(guild)
            logger.info("Auto-sync completed: %s success, %s failed", result.get("success", 0), result.get("failed", 0))
            try:
                await self.db.log_audit(
                    action="sync_auto",
                    details=f"success={result.get('success', 0)}, failed={result.get('failed', 0)}",
                )
            except Exception:
                logger.exception("Failed to log auto-sync")
            if result.get("failed", 0) > 0:
                await self._notify_admin_auto_sync(result)
        except Exception:
            logger.exception("Auto-sync run failed")

    async def post_media_notification(self, channel_id: str | None, source: str, title: str, media_type: str | None, summary: str | None, year: int | None, thumb: str | None):
        if not channel_id:
            logger.debug("No channel ID configured for %s media notifications", source)
            return
        try:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                logger.warning("Media notification channel %s not found", channel_id)
                return
            embed = discord.Embed(
                title=f"Nouveau média sur {source}",
                description=f"**{title}**" + (f" ({year})" if year else ""),
                color=discord.Color.green(),
            )
            if media_type:
                embed.add_field(name="Type", value=media_type.capitalize(), inline=True)
            if summary:
                embed.add_field(name="Résumé", value=summary[:1024], inline=False)
            if thumb:
                embed.set_thumbnail(url=thumb)
            await channel.send(embed=embed)
            logger.info("Sent %s media notification for %s", source, title)
        except Exception:
            logger.exception("Failed to post %s media notification", source)

    async def handle_overseerr_webhook(self, payload: dict):
        try:
            notification_type = payload.get("notification_type", "UNKNOWN")
            subject = payload.get("subject", "Notification Overseerr")
            message = payload.get("message", "")
            image = payload.get("image")
            media = payload.get("media", {})
            request_info = payload.get("request", {})
            requested_by = request_info.get("requestedBy", {}) if request_info else {}
            overseerr_discord_id = requested_by.get("discordId") or requested_by.get("discord_id")

            overseerr_channel_id = os.getenv("OVERSEERR_WEBHOOK_CHANNEL_ID")
            if overseerr_channel_id:
                channel = self.bot.get_channel(int(overseerr_channel_id))
                if channel:
                    embed = discord.Embed(
                        title=f"Overseerr — {subject}",
                        description=message[:2048],
                        color=discord.Color.blue(),
                    )
                    if media:
                        embed.add_field(name="Média", value=media.get("title") or "N/A", inline=True)
                        if media.get("year"):
                            embed.add_field(name="Année", value=str(media.get("year")), inline=True)
                        if media.get("type"):
                            embed.add_field(name="Type", value=media.get("type"), inline=True)
                    if image:
                        embed.set_thumbnail(url=image)
                    await channel.send(embed=embed)

            if notification_type == "MEDIA_AVAILABLE" and overseerr_discord_id:
                try:
                    user_obj = await self.bot.fetch_user(int(overseerr_discord_id))
                    if user_obj:
                        title = media.get("title") or "Nouveau média"
                        await user_obj.send(
                            f"🎉 Bonne nouvelle ! **{title}** est maintenant disponible sur {BOT_NAME}."
                        )
                except discord.Forbidden:
                    logger.warning("Cannot DM user %s for media available notification", overseerr_discord_id)
                except Exception:
                    logger.exception("Failed to notify user %s about available media", overseerr_discord_id)

            try:
                await self.db.log_audit(
                    action=f"overseerr_{notification_type.lower()}",
                    discord_id=str(overseerr_discord_id) if overseerr_discord_id else None,
                    details=f"subject={subject}, media={media.get('title')}",
                )
            except Exception:
                logger.exception("Failed to log Overseerr webhook")
        except Exception:
            logger.exception("Failed to handle Overseerr webhook")

    async def _notify_admin_auto_sync(self, result: dict):
        try:
            admin = await self.bot.fetch_user(self.admin_id)
            if admin is None:
                return
            errors = "\n".join(result.get("errors", [])[:5])
            await admin.send(
                f"⚠️ Auto-sync terminé avec {result.get('failed', 0)} échecs sur {result.get('success', 0) + result.get('failed', 0)} utilisateurs.\n{errors}"
            )
        except discord.Forbidden:
            logger.warning("Cannot notify admin via DM")
        except Exception:
            logger.exception("Failed to notify admin about auto-sync")

    def register_platform_handler(self, platform_tag: str, handler):
        self.platform_handlers[platform_tag] = handler

    async def wait_until_closed(self):
        if self._bot_task:
            try:
                await self._bot_task
            except asyncio.CancelledError:
                logger.info("Bot task was cancelled")
            except Exception:
                logger.exception("Bot task ended with exception")

    def _slugify_display_name(self, display_name: str) -> str:
        value = (display_name or "user").strip().lower()
        value = re.sub(r"\s+", "-", value)
        value = re.sub(r"[^a-z0-9\-]", "", value)
        value = re.sub(r"-+", "-", value).strip("-")
        value = value[:80]
        return value or "user"

    def _build_channel_name_candidates(self, platform_tag: str, display_name: str):
        safe_name = self._slugify_display_name(display_name)
        emoji_marker = PLATFORM_CHANNEL_MARKERS.get(platform_tag, platform_tag.lower())
        ascii_prefix = PLATFORM_ASCII_PREFIXES.get(platform_tag, platform_tag.lower())

        emoji_base = f"{emoji_marker}-{safe_name}".lower()
        ascii_base = f"{ascii_prefix}-{safe_name}".lower()

        emoji_candidates = [emoji_base] + [f"{emoji_base}-{i}" for i in range(1, 100)]
        ascii_candidates = [ascii_base] + [f"{ascii_base}-{i}" for i in range(1, 100)]
        return emoji_candidates + ascii_candidates

    async def ensure_inbox_category(self):
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild is None:
                guild = await self.bot.fetch_guild(self.guild_id)
            category = discord.utils.get(guild.categories, name=INBOX_CATEGORY_NAME)
            if category is None:
                category = await guild.create_category(INBOX_CATEGORY_NAME)
            return category
        except discord.Forbidden:
            logger.exception("Bot lacks permissions to manage channels/categories in the guild")
            raise
        except Exception:
            logger.exception("Failed to ensure INBOX category")
            raise

    async def get_or_create_channel_for(self, platform_tag: str, platform_user_id: str, display_name: str):
        candidates = self._build_channel_name_candidates(platform_tag, display_name)
        logger.debug("Resolving channel for %s user=%s display_name=%s (candidates=%s)", platform_tag, platform_user_id, display_name, len(candidates))
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild is None:
                guild = await self.bot.fetch_guild(self.guild_id)
            category = await self.ensure_inbox_category()

            existing_for_mapping = await self.db.get_mapping(platform_tag, platform_user_id)
            if existing_for_mapping:
                existing_channel = guild.get_channel(existing_for_mapping)
                if existing_channel:
                    logger.debug("Found existing channel %s for %s user=%s", existing_channel.id, platform_tag, platform_user_id)
                    return existing_channel
                logger.debug("Mapped channel %s no longer exists for %s user=%s", existing_for_mapping, platform_tag, platform_user_id)

            for candidate_name in candidates:
                existing = discord.utils.get(category.text_channels, name=candidate_name)
                if existing:
                    existing_mapping = await self.db.get_mapping_by_channel(existing.id)
                    if existing_mapping == (platform_tag, platform_user_id):
                        await self.db.set_mapping(platform_tag, platform_user_id, existing.id)
                        return existing
                    continue

                try:
                    channel = await guild.create_text_channel(candidate_name, category=category)
                    await self.db.set_mapping(platform_tag, platform_user_id, channel.id)
                    logger.info("Created channel %s (%s) for %s user=%s", channel.id, candidate_name, platform_tag, platform_user_id)
                    return channel
                except Exception:
                    logger.warning("Failed to create channel with name '%s', trying next candidate", candidate_name)
                    continue

            raise RuntimeError("Unable to create a unique channel name")
        except discord.Forbidden:
            logger.exception("Bot lacks permission to create or access channel")
            raise
        except Exception:
            logger.exception("Failed to get or create channel")
            raise

    async def post_inbound_message(self, platform_tag: str, platform_user_id: str, display_name: str, text: str, attachments=None):
        try:
            channel = await self.get_or_create_channel_for(platform_tag, platform_user_id, display_name)
            logger.debug("Posting inbound %s message from %s to channel %s", platform_tag, platform_user_id, channel.id)
            author = f"[{platform_tag}]{display_name}"
            files = []
            temp_paths = []
            if attachments:
                for att in attachments:
                    try:
                        if 'bytes' in att:
                            bio = io.BytesIO(att['bytes'])
                            bio.seek(0)
                            filename = att.get('filename') or 'file'
                            files.append(discord.File(fp=bio, filename=filename))
                        elif 'path' in att:
                            fp = open(att['path'], 'rb')
                            files.append(discord.File(fp=fp, filename=att.get('filename') or os.path.basename(att['path'])))
                            temp_paths.append({'path': att['path'], 'fp': fp})
                    except Exception:
                        logger.exception("Failed to prepare attachment for Discord")
            original_content = f"**{author}**: {text}" if text else f"**{author}**"
            content = _truncate_text_for_discord(text, author)
            if content != original_content:
                logger.debug("Truncated inbound message from %s to %s characters for Discord", len(original_content), len(content))

            try:
                if files:
                    await channel.send(content, files=files)
                else:
                    await channel.send(content)
            finally:
                for t in temp_paths:
                    try:
                        t['fp'].close()
                    except Exception:
                        pass
                    try:
                        os.unlink(t['path'])
                    except Exception:
                        pass

            answered = False
            if self.auto_responder and text:
                user_data = await self._get_user_data_for_inbound(platform_tag, platform_user_id)
                answered = await self._send_auto_response(platform_tag, platform_user_id, channel, text, user_data)

            if not answered and platform_tag == "DC":
                await self._notify_admin_unanswered(platform_user_id, text)

            await self._bump_channel_to_top(channel)
        except Exception:
            logger.exception("Failed to post inbound message to Discord")

    async def _notify_admin_unanswered(self, discord_id: str, text: str):
        if not self.onboarding.config.support_dm_enabled:
            return
        try:
            admin = await self.bot.fetch_user(self.admin_id)
            if admin is None:
                return
            await admin.send(
                f"[Message en attente - {BOT_NAME}] de <@{discord_id}> (Discord ID: {discord_id}):\n{text[:1500]}"
            )
            logger.info("Notified admin about unanswered DM from user %s", discord_id)
        except discord.Forbidden:
            logger.warning("Cannot notify admin via DM")
        except Exception:
            logger.exception("Failed to notify admin about unanswered DM")
