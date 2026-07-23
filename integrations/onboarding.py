"""Onboarding flow for new Discord community members.

Handles:
- Detecting when a new member finishes Discord's native community onboarding.
- Checking whether the Discord ID is already linked locally or in Overseerr.
- Sending a DM with a button to link a Seerr account via email.
- Creating/assigning the "Abonné" role once linked.
- Sending a final confirmation DM with support info.
"""
import os
import json
import datetime
import logging
import discord
from discord import ui

logger = logging.getLogger(__name__)
BOT_NAME = os.getenv("BOT_NAME", "Akasha")


class OnboardingConfig:
    def __init__(self):
        self.enabled = os.getenv("ONBOARDING_DM_ENABLED", "true").lower() in ("1", "true", "yes")
        self.member_role_name = os.getenv("MEMBER_ROLE_NAME", "Abonné")
        self.create_role = os.getenv("CREATE_MEMBER_ROLE", "true").lower() in ("1", "true", "yes")
        self.seerr_signup_url = os.getenv("SEERR_SIGNUP_URL", "https://s.akasha.ing")
        self.plex_url = os.getenv("PLEX_URL", "https://p.akasha.ing")
        self.jellyfin_url = os.getenv("JELLYFIN_URL", "https://j.akasha.ing")
        self.support_dm_enabled = os.getenv("SUPPORT_DM_ENABLED", "true").lower() in ("1", "true", "yes")
        self.verification_role_name = os.getenv("VERIFICATION_ROLE_NAME", "À vérifier")
        self.verification_channel_name = os.getenv("VERIFICATION_CHANNEL_NAME", "verification")
        self.trial_role_name = os.getenv("TRIAL_ROLE_NAME", "Essai")
        self.expired_role_name = os.getenv("EXPIRED_ROLE_NAME", "Expiré")
        self.expiration_channel_name = os.getenv("EXPIRATION_CHANNEL_NAME", "abonnement-expire")
        self.answer_role_names = tuple(
            name.strip() for name in os.getenv("ONBOARDING_ANSWER_ROLE_NAMES", "Q1,Q2,Q3").split(",") if name.strip()
        )


async def ensure_member_role(guild: discord.Guild, config: OnboardingConfig) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=config.member_role_name)
    if role:
        return role
    if not config.create_role:
        logger.error("Member role %r not found and CREATE_MEMBER_ROLE is disabled", config.member_role_name)
        return None
    try:
        role = await guild.create_role(
            name=config.member_role_name,
            color=discord.Color.gold(),
            reason="Auto-created by Akasha onboarding bot",
        )
        logger.info("Created member role %s (%s)", role.id, role.name)
        return role
    except Exception:
        logger.exception("Failed to create member role %r", config.member_role_name)
        return None


async def assign_member_role(member: discord.Member, config: OnboardingConfig) -> bool:
    if not config.enabled:
        return False
    try:
        role = await ensure_member_role(member.guild, config)
        if not role:
            return False
        if role in member.roles:
            return True
        await member.add_roles(role, reason=f"{BOT_NAME} onboarding completed")
        logger.info("Assigned member role %s to user %s", role.name, member.id)
        return True
    except Exception:
        logger.exception("Failed to assign member role to user %s", member.id)
        return False


async def ensure_verification_role(guild: discord.Guild, config: OnboardingConfig) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=config.verification_role_name)
    if role:
        return role
    try:
        role = await guild.create_role(
            name=config.verification_role_name,
            color=discord.Color.light_grey(),
            reason=f"Auto-created by {BOT_NAME} onboarding bot",
        )
        logger.info("Created verification role %s (%s)", role.id, role.name)
        return role
    except Exception:
        logger.exception("Failed to create verification role %r", config.verification_role_name)
        return None


async def assign_verification_role(member: discord.Member, config: OnboardingConfig) -> bool:
    try:
        role = await ensure_verification_role(member.guild, config)
        if not role:
            return False
        if role in member.roles:
            return True
        await member.add_roles(role, reason=f"{BOT_NAME} account verification required")
        logger.info("Assigned verification role %s to user %s", role.name, member.id)
        return True
    except Exception:
        logger.exception("Failed to assign verification role to user %s", member.id)
        return False


async def remove_verification_role(member: discord.Member, config: OnboardingConfig) -> bool:
    role = discord.utils.get(member.guild.roles, name=config.verification_role_name)
    if not role or role not in member.roles:
        return True
    try:
        await member.remove_roles(role, reason=f"{BOT_NAME} account verification completed")
        logger.info("Removed verification role %s from user %s", role.name, member.id)
        return True
    except Exception:
        logger.exception("Failed to remove verification role from user %s", member.id)
        return False


async def ensure_named_role(guild: discord.Guild, name: str, color: discord.Color) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=name)
    if role:
        return role
    try:
        role = await guild.create_role(
            name=name,
            color=color,
            hoist=False,
            mentionable=False,
            reason=f"Auto-created by {BOT_NAME} access management",
        )
        logger.info("Created managed role %s (%s)", role.id, role.name)
        return role
    except Exception:
        logger.exception("Failed to create managed role %r", name)
        return None


async def ensure_access_roles(guild: discord.Guild, config: OnboardingConfig) -> dict[str, discord.Role]:
    roles = {}
    for key, name, color in (
        ("subscriber", config.member_role_name, discord.Color.gold()),
        ("trial", config.trial_role_name, discord.Color.blurple()),
        ("expired", config.expired_role_name, discord.Color.dark_grey()),
    ):
        role = await ensure_named_role(guild, name, color)
        if role:
            roles[key] = role
    for name in config.answer_role_names:
        await ensure_named_role(guild, name, discord.Color.default())
    return roles


async def remove_onboarding_answer_roles(member: discord.Member, config: OnboardingConfig) -> bool:
    roles = [role for role in member.roles if role.name in config.answer_role_names]
    if not roles:
        return True
    try:
        await member.remove_roles(*roles, reason=f"{BOT_NAME} onboarding completed")
        logger.info("Removed temporary onboarding roles from user %s", member.id)
        return True
    except Exception:
        logger.exception("Failed to remove temporary onboarding roles from user %s", member.id)
        return False


async def assign_access_role(member: discord.Member, config: OnboardingConfig, access_type: str = "subscriber", expired: bool = False) -> bool:
    try:
        roles = await ensure_access_roles(member.guild, config)
        target_key = "expired" if expired else "trial" if access_type == "trial" else "subscriber"
        target = roles.get(target_key)
        if not target:
            return False
        managed = [role for role in roles.values() if role in member.roles and role != target]
        if managed:
            await member.remove_roles(*managed, reason=f"{BOT_NAME} access role updated")
        if target not in member.roles:
            await member.add_roles(target, reason=f"{BOT_NAME} access role updated")
        await remove_verification_role(member, config)
        await remove_onboarding_answer_roles(member, config)
        logger.info("Assigned %s access role to user %s", target.name, member.id)
        return True
    except Exception:
        logger.exception("Failed to assign access role to user %s", member.id)
        return False


class LinkEmailModal(ui.Modal, title=f"Lier mon compte Seerr - {BOT_NAME}"):
    email = ui.TextInput(
        label="Email",
        placeholder="ton@email.com",
        required=True,
        max_length=320,
    )

    def __init__(self, flow, member: discord.Member):
        super().__init__()
        self.flow = flow
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        email = str(self.email).lower().strip()
        logger.info("Link modal submitted by user %s", self.member.id)
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self.flow.process_email_link(self.member, email, interaction)
        if not success:
            # Show the signup option again if email not found
            view = OnboardingView(self.flow, self.member, show_signup=True)
            await interaction.followup.send(
                f"Cet email n'a pas été trouvé sur Seerr. "
                f"Si tu n'as pas encore de compte, crée-le via le bouton ci-dessous puis reviens lier ton email.",
                view=view,
                ephemeral=True,
            )


class OnboardingView(ui.View):
    def __init__(self, flow, member: discord.Member, show_signup: bool = False):
        super().__init__(timeout=None)
        self.flow = flow
        self.member = member
        self.show_signup = show_signup

        link_btn = ui.Button(
            label="Lier mon compte Seerr",
            style=discord.ButtonStyle.primary,
            custom_id="onboarding:link",
        )
        link_btn.callback = self._on_link_click
        self.add_item(link_btn)

        if show_signup:
            signup_btn = ui.Button(
                label="Créer mon compte Seerr",
                style=discord.ButtonStyle.link,
                url=flow.config.seerr_signup_url,
            )
            self.add_item(signup_btn)

    async def _on_link_click(self, interaction: discord.Interaction):
        await _handle_link_click(self.flow, interaction)


class PersistentOnboardingView(ui.View):
    """Persistent view registered globally so the link button works after bot restarts."""

    def __init__(self, flow):
        super().__init__(timeout=None)
        self.flow = flow

    @ui.button(
        label="Lier mon compte Seerr",
        style=discord.ButtonStyle.primary,
        custom_id="onboarding:link",
    )
    async def link_callback(self, interaction: discord.Interaction, _button: ui.Button):
        await _handle_link_click(self.flow, interaction)


async def _handle_link_click(flow, interaction: discord.Interaction):
    member = None
    try:
        guild = flow.discord_bridge.bot.get_guild(flow.discord_bridge.guild_id)
        if guild is None:
            guild = await flow.discord_bridge.bot.fetch_guild(flow.discord_bridge.guild_id)
        member = guild.get_member(interaction.user.id)
        if member is None:
            member = await guild.fetch_member(interaction.user.id)
    except Exception:
        logger.exception("Failed to resolve guild member for interaction user %s", interaction.user.id)
        await interaction.response.send_message(
            f"Je n'arrive pas à te trouver sur le serveur. Rejoins le serveur Discord {BOT_NAME} d'abord.",
            ephemeral=True,
        )
        return

    if member.bot:
        await interaction.response.send_message("Ce bouton est réservé aux humains.", ephemeral=True)
        return

    existing = await flow.db.get_user_by_discord_id(str(member.id))
    if existing and existing.get("overseerr_id"):
        await flow.apply_access(member, existing)
        await interaction.response.send_message("Ton compte est déjà lié. Tes accès membre sont actifs.", ephemeral=True)
        return

    if flow.overseerr_client:
        try:
            overseerr_user = await flow.overseerr_client.find_user_by_discord_id(str(member.id))
            if overseerr_user:
                await flow._link_overseerr_user(member, overseerr_user)
                await interaction.response.send_message("Ton compte est déjà lié. Tes accès membre sont actifs.", ephemeral=True)
                return
        except Exception:
            logger.exception("Failed to look up linked Seerr account for user %s", member.id)

    await interaction.response.send_modal(LinkEmailModal(flow, member))


class OnboardingFlow:
    def __init__(self, discord_bridge, overseerr_client, db):
        self.discord_bridge = discord_bridge
        self.overseerr_client = overseerr_client
        self.db = db
        self.config = OnboardingConfig()
        self._pending = set()  # member ids currently in the onboarding flow

    def register_persistent_views(self, bot):
        bot.add_view(PersistentOnboardingView(self))
        logger.info("Registered persistent onboarding view")

    async def ensure_expiration_channel(self, guild: discord.Guild):
        roles = await ensure_access_roles(guild, self.config)
        expired_role = roles.get("expired")
        if not expired_role:
            return None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            expired_role: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False),
        }
        channel = discord.utils.get(guild.text_channels, name=self.config.expiration_channel_name)
        try:
            if channel is None:
                channel = await guild.create_text_channel(
                    self.config.expiration_channel_name,
                    overwrites=overwrites,
                    reason=f"Auto-created by {BOT_NAME} access management",
                )
                logger.info("Created expiration channel %s (%s)", channel.id, channel.name)
            else:
                await channel.edit(overwrites=overwrites, reason=f"Managed by {BOT_NAME} access management")

            found_message = False
            async for message in channel.history(limit=50):
                if message.author.id == self.discord_bridge.bot.user.id and message.embeds:
                    if message.embeds[0].title == f"Accès expiré — {BOT_NAME}":
                        found_message = True
                        break
            if not found_message:
                embed = discord.Embed(
                    title=f"Accès expiré — {BOT_NAME}",
                    description=(
                        "Ton accès est arrivé à expiration. Pour le réactiver, contacte "
                        "<@1521192140494078123> en message privé, Telegram `@akasha_stream_bot` "
                        "ou WhatsApp `@akasha.ing`."
                    ),
                    color=discord.Color.dark_grey(),
                )
                await channel.send(embed=embed)
            return channel
        except Exception:
            logger.exception("Failed to create or configure expiration channel")
            return None

    async def ensure_verification_channel(self, guild: discord.Guild):
        if not self.config.enabled:
            return None
        await ensure_access_roles(guild, self.config)
        await self.ensure_expiration_channel(guild)
        role = await ensure_verification_role(guild, self.config)
        if not role:
            return None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False),
        }
        channel = discord.utils.get(guild.text_channels, name=self.config.verification_channel_name)
        try:
            if channel is None:
                channel = await guild.create_text_channel(
                    self.config.verification_channel_name,
                    overwrites=overwrites,
                    reason=f"Auto-created by {BOT_NAME} onboarding bot",
                )
                logger.info("Created verification channel %s (%s)", channel.id, channel.name)
            else:
                await channel.edit(overwrites=overwrites, reason=f"Managed by {BOT_NAME} onboarding bot")

            found_message = False
            async for message in channel.history(limit=50):
                if message.author.id == self.discord_bridge.bot.user.id and message.embeds:
                    if message.embeds[0].title == f"Vérifie ton compte {BOT_NAME}":
                        found_message = True
                        break
            if not found_message:
                embed = discord.Embed(
                    title=f"Vérifie ton compte {BOT_NAME}",
                    description=(
                        "Pour accéder aux salons réservés aux membres, lie ton compte Seerr à Discord. "
                        "Clique sur le bouton ci-dessous : ton adresse e-mail reste privée."
                    ),
                    color=discord.Color.blue(),
                )
                await channel.send(embed=embed, view=PersistentOnboardingView(self))
            return channel
        except Exception:
            logger.exception("Failed to create or configure verification channel")
            return None

    async def capture_onboarding_answers(self, member: discord.Member):
        answers = sorted(role.name for role in member.roles if role.name in self.config.answer_role_names)
        if answers:
            await self.db.record_onboarding_answers(str(member.id), json.dumps(answers))
            logger.info("Recorded onboarding answers for user %s", member.id)

    @staticmethod
    def _is_expired(user_data: dict | None) -> bool:
        expires = (user_data or {}).get("wizarr_invite_expires")
        if not expires:
            return False
        try:
            expires_at = datetime.datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            return expires_at <= datetime.datetime.now(datetime.timezone.utc)
        except (TypeError, ValueError):
            return False

    async def apply_access(self, member: discord.Member, user_data: dict | None):
        access_type = (user_data or {}).get("access_type") or "subscriber"
        expired = self._is_expired(user_data)
        if expired:
            await self.ensure_expiration_channel(member.guild)
        return await assign_access_role(member, self.config, access_type, expired)

    def is_pending(self, member_id: int) -> bool:
        return member_id in self._pending

    async def _send_dm(self, member: discord.Member, content: str = None, embed: discord.Embed = None, view: ui.View = None):
        try:
            if embed:
                await member.send(content=content, embed=embed, view=view)
            elif content:
                await member.send(content=content, view=view)
            logger.info("Sent onboarding DM to user %s", member.id)
            return True
        except discord.Forbidden:
            logger.warning("Cannot send DM to user %s (DMs disabled)", member.id)
            return False
        except Exception:
            logger.exception("Failed to send onboarding DM to user %s", member.id)
            return False

    async def start(self, member: discord.Member):
        if not self.config.enabled:
            return
        if member.bot:
            return
        if self.is_pending(member.id):
            return

        self._pending.add(member.id)
        logger.info("Starting onboarding flow for user %s", member.id)

        # Check local DB first
        existing = await self.db.get_user_by_discord_id(str(member.id))
        if existing and existing.get("overseerr_id"):
            await self._finish_onboarding(member, existing)
            self._pending.discard(member.id)
            return

        # Check Seerr by Discord ID
        if self.overseerr_client:
            try:
                overseerr_user = await self.overseerr_client.find_user_by_discord_id(str(member.id))
                if overseerr_user:
                    await self._link_overseerr_user(member, overseerr_user)
                    self._pending.discard(member.id)
                    return
            except Exception:
                logger.exception("Failed to search Seerr by Discord ID for user %s", member.id)

        await self.ensure_verification_channel(member.guild)
        await assign_verification_role(member, self.config)

        # Send welcome DM with link button
        embed = discord.Embed(
            title=f"Bienvenue sur {BOT_NAME}",
            description=(
                f"Merci d'avoir rejoint le serveur Discord {BOT_NAME}. "
                f"Pour accéder aux salons réservés aux membres, lie ton compte Seerr à ton Discord."
            ),
            color=discord.Color.blue(),
        )
        view = OnboardingView(self, member)
        await self._send_dm(member, embed=embed, view=view)
        self._pending.discard(member.id)

    async def process_email_link(self, member: discord.Member, email: str, interaction: discord.Interaction | None = None) -> bool:
        if not self.overseerr_client:
            if interaction:
                await interaction.followup.send(
                    f"La liaison Seerr n'est pas configurée. Contacte l'équipe {BOT_NAME}.", ephemeral=True
                )
            return False

        try:
            overseerr_user = await self.overseerr_client.find_user_by_email(email)
            if not overseerr_user:
                logger.info("No Overseerr account found for user %s", member.id)
                return False

            await self._link_overseerr_user(member, overseerr_user, email=email)
            if interaction:
                await interaction.followup.send(
                    f"Compte lié avec succès. Le rôle membre t'a été attribué. Bienvenue chez {BOT_NAME} !", ephemeral=True
                )
            return True
        except Exception:
            logger.exception("Failed to process email link for user %s", member.id)
            if interaction:
                await interaction.followup.send(
                    f"Une erreur s'est produite pendant la liaison. Réessaie plus tard ou contacte l'équipe {BOT_NAME}.", ephemeral=True
                )
            return False

    async def _link_overseerr_user(self, member: discord.Member, overseerr_user: dict, email: str | None = None):
        overseerr_id = overseerr_user.get("id")
        email = email or overseerr_user.get("email", "").lower().strip()
        plex_username = overseerr_user.get("plexUsername")

        try:
            await self.overseerr_client.update_user_discord_id(overseerr_id, str(member.id))
        except Exception:
            logger.exception("Failed to update Discord ID in Overseerr for user %s", member.id)

        now = datetime.datetime.utcnow().isoformat()
        existing = await self.db.get_user_by_discord_id(str(member.id))
        user_fields = {
            "email": email,
            "discord_username": member.name,
            "overseerr_id": overseerr_id,
            "overseerr_username": overseerr_user.get("username") or overseerr_user.get("displayName"),
            "overseerr_plex_username": plex_username,
            "overseerr_discord_ids": str(member.id),
            "updated_at": now,
        }
        if existing:
            await self.db.update_user(str(member.id), **user_fields)
        else:
            await self.db.set_user(
                discord_id=str(member.id),
                created_at=now,
                access_type="subscriber",
                **user_fields,
            )

        await self._finish_onboarding(member, await self.db.get_user_by_discord_id(str(member.id)))

    async def _finish_onboarding(self, member: discord.Member, user_data: dict):
        await self.apply_access(member, user_data)
        access_type = (user_data or {}).get("access_type") or "subscriber"
        expired = self._is_expired(user_data)

        if expired:
            expires = (user_data or {}).get("wizarr_invite_expires") or "date inconnue"
            lines = [
                "Ton accès Akasha a expiré.",
                f"Date d'expiration : `{expires}`.",
                "Pour le réactiver, contacte <@1521192140494078123> en message privé, Telegram `@akasha_stream_bot` ou WhatsApp `@akasha.ing`.",
            ]
        else:
            role_label = "Essai" if access_type == "trial" else "Abonné"
            lines = [
                "Ton inscription a bien été finalisée et ton compte Discord a été lié.",
                f"Tu as maintenant accès aux salons réservés aux {role_label}s.",
            ]
        if user_data and user_data.get("overseerr_plex_username"):
            lines.append(f"Compte Plex lié : `{user_data['overseerr_plex_username']}`")

        links = []
        if self.config.plex_url:
            links.append(f"- Plex : {self.config.plex_url}")
        if self.config.jellyfin_url:
            links.append(f"- Jellyfin : {self.config.jellyfin_url}")
        if self.config.seerr_signup_url:
            links.append(f"- Seerr : {self.config.seerr_signup_url}")
        if links:
            lines.append("\nLiens utiles :")
            lines.extend(links)

        lines.append("\nCommandes disponibles :")
        lines.append("- `/account` — voir tes infos et ton expiration")
        lines.append("- `/request <titre>` — demander un film/série")
        lines.append("- `/renew` — demander le renouvellement")
        lines.append("- `/support <sujet> <description>` — contacter l'équipe")
        lines.append("- `/faq` — questions fréquentes")

        lines.append(
            f"\nSi tu as des questions, écris-moi directement ici en réponse à ce message. "
            f"L'équipe {BOT_NAME} te répondra ou te mettra en relation avec un admin."
        )

        embed = discord.Embed(
            title=f"Bienvenue parmi les Abonnés {BOT_NAME}",
            description="\n".join(lines),
            color=discord.Color.green(),
        )
        await self._send_dm(member, embed=embed)
