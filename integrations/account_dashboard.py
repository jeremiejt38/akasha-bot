import datetime
import os
import discord
from discord import ui


class AccountPanel(ui.View):
    def __init__(self, dashboard, preferences=None):
        super().__init__(timeout=None)
        self.dashboard = dashboard
        self.preferences = preferences or {}
        self._add_refresh()
        self._add_toggle("DM problèmes", "dm_problem_notifications", "account:dm:problems")
        self._add_toggle("DM demandes", "dm_request_notifications", "account:dm:requests")

    def _add_refresh(self):
        button = ui.Button(label="Actualiser", style=discord.ButtonStyle.primary, custom_id="account:refresh")

        async def callback(interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            embed = await self.dashboard.build_embed(interaction.user.id)
            await interaction.followup.send(embed=embed, ephemeral=True)
            await self.dashboard.move_panel_to_bottom(interaction.channel, interaction.message)

        button.callback = callback
        self.add_item(button)

    def _add_toggle(self, label, field, custom_id):
        enabled = bool(self.preferences.get(field, 1))
        button = ui.Button(
            label=label,
            style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
            custom_id=custom_id,
        )

        async def callback(interaction):
            await interaction.response.defer(ephemeral=True)
            user = await self.dashboard.db.get_user_by_discord_id(str(interaction.user.id)) or {}
            enabled = not bool(user.get(field, 1))
            await self.dashboard.db.update_notification_preferences(str(interaction.user.id), **{field: enabled})
            user[field] = int(enabled)
            await interaction.followup.send(f"{label} {'activés' if enabled else 'désactivés'}.", ephemeral=True)
            await self.dashboard.move_panel_to_bottom(interaction.channel, interaction.message, user)

        button.callback = callback
        self.add_item(button)


class AccountDashboard:
    def __init__(self, bridge, db, overseerr_client, tautulli_client=None):
        self.bridge = bridge
        self.db = db
        self.overseerr_client = overseerr_client
        self.tautulli_client = tautulli_client

    async def ensure_channel(self, guild):
        role_names = (
            os.getenv("TRIAL_ROLE_NAME", "Essai"),
            os.getenv("MEMBER_ROLE_NAME", "Abonné"),
            os.getenv("EXPIRED_ROLE_NAME", "Expiré"),
        )
        category = discord.utils.get(guild.categories, name="Akasha") or await guild.create_category("Akasha")
        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        for role_name in role_names:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False)
        channel = discord.utils.get(category.text_channels, name="mon-compte")
        if channel is None:
            channel = await guild.create_text_channel("mon-compte", category=category, overwrites=overwrites, reason="Akasha account dashboard")
        else:
            await channel.edit(overwrites=overwrites, reason="Managed by Akasha account dashboard")
        async for message in channel.history(limit=30):
            if message.author.id == self.bridge.bot.user.id and message.components:
                return channel
        embed = discord.Embed(
            title="Mon compte Akasha",
            description="Consulte tes informations, tes statistiques et tes préférences avec les boutons ci-dessous.",
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed, view=AccountPanel(self))
        return channel

    async def move_panel_to_bottom(self, channel, panel_message, preferences=None):
        await panel_message.delete()
        embed = discord.Embed(
            title="Mon compte Akasha",
            description="Consulte tes informations, tes statistiques et tes préférences avec les boutons ci-dessous.",
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed, view=AccountPanel(self, preferences))

    async def build_embed(self, discord_id):
        user = await self.db.get_user_by_discord_id(str(discord_id))
        embed = discord.Embed(title="Mon compte Akasha", color=discord.Color.blue())
        if not user:
            embed.description = "Ton compte n'est pas encore lié à Seerr. Utilise #verification pour le lier."
            return embed

        requests = await self._request_stats(user.get("overseerr_id"))
        problems = await self.db.get_problem_report_counts(str(discord_id))
        tautulli = await self._tautulli_stats(user.get("email"))
        expires = user.get("wizarr_invite_expires")
        days = self._days_remaining(expires)
        embed.add_field(name="Date d'inscription", value=self._format_date(user.get("created_at")), inline=True)
        embed.add_field(name="Expiration actuelle", value=self._format_date(expires), inline=True)
        embed.add_field(name="Jours restants", value=str(days) if days is not None else "Illimité / inconnue", inline=True)
        embed.add_field(name="Demandes", value=str(requests["total"]), inline=True)
        embed.add_field(name="Demandes disponibles", value=str(requests["available"]), inline=True)
        embed.add_field(name="Problèmes signalés", value=str(problems["total"]), inline=True)
        embed.add_field(name="Problèmes en attente", value=str(problems["open"]), inline=True)
        embed.add_field(name="Films regardés", value=str(tautulli["movies"]) if tautulli else "Non disponible", inline=True)
        embed.add_field(name="Épisodes regardés", value=str(tautulli["episodes"]) if tautulli else "Non disponible", inline=True)
        embed.add_field(name="Temps de visionnage", value=self._format_duration(tautulli["total_seconds"]) if tautulli else "Non disponible", inline=True)
        return embed

    async def _request_stats(self, overseerr_id):
        if not self.overseerr_client or not overseerr_id:
            return {"total": 0, "available": 0}
        total = available = page = 0
        while True:
            data = await self.overseerr_client._request(
                "GET", "/request", params={"requestedBy": overseerr_id, "take": 20, "skip": page * 20}
            )
            results = data.get("results", [])
            total += len(results)
            available += sum(1 for request in results if (request.get("media") or {}).get("status") == 5)
            page_info = data.get("pageInfo") or {}
            if page + 1 >= page_info.get("pages", 1):
                return {"total": total, "available": available}
            page += 1

    async def _tautulli_stats(self, email):
        if not self.tautulli_client:
            return None
        try:
            return await self.tautulli_client.get_user_statistics_by_email(email)
        except Exception:
            return None

    @staticmethod
    def _format_duration(seconds):
        days, remaining = divmod(seconds, 86400)
        hours = remaining // 3600
        return f"{days} j {hours} h"

    @staticmethod
    def _format_date(value):
        if not value:
            return "Inconnue"
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%y")
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _days_remaining(value):
        if not value:
            return None
        try:
            expires = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            return max(0, (expires - datetime.datetime.now(datetime.timezone.utc)).days)
        except (TypeError, ValueError):
            return None
