import datetime
import os
import discord
from discord import ui


class AccountPanel(ui.View):
    def __init__(self, dashboard):
        super().__init__(timeout=None)
        self.dashboard = dashboard

    @ui.button(label="Voir mon compte", style=discord.ButtonStyle.primary, custom_id="account:show")
    async def show(self, interaction, _button):
        embed = await self.dashboard.build_embed(interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.dashboard.move_panel_to_bottom(interaction.channel, interaction.message)

    @ui.button(label="Préférences DM", style=discord.ButtonStyle.secondary, custom_id="account:preferences")
    async def preferences(self, interaction, _button):
        user = await self.dashboard.db.get_user_by_discord_id(str(interaction.user.id)) or {}
        await interaction.response.send_message(
            "Configure tes notifications :",
            view=NotificationPreferencesView(self.dashboard, user),
            ephemeral=True,
        )
        await self.dashboard.move_panel_to_bottom(interaction.channel, interaction.message)


class NotificationPreferencesView(ui.View):
    def __init__(self, dashboard, user):
        super().__init__(timeout=300)
        self.dashboard = dashboard
        self.user = user
        self._add_toggle("Problèmes", "dm_problem_notifications", user.get("dm_problem_notifications", 1))
        self._add_toggle("Demandes disponibles", "dm_request_notifications", user.get("dm_request_notifications", 1))

    def _add_toggle(self, label, field, enabled):
        button = ui.Button(
            label=f"{label} : {'activés' if enabled else 'désactivés'}",
            style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
        )

        async def callback(interaction):
            new_value = not bool(self.user.get(field, 1))
            self.user[field] = int(new_value)
            await self.dashboard.db.update_notification_preferences(str(interaction.user.id), **{field: new_value})
            await interaction.response.edit_message(view=NotificationPreferencesView(self.dashboard, self.user))

        button.callback = callback
        self.add_item(button)


class AccountDashboard:
    def __init__(self, bridge, db, overseerr_client):
        self.bridge = bridge
        self.db = db
        self.overseerr_client = overseerr_client

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

    async def move_panel_to_bottom(self, channel, panel_message):
        await panel_message.delete()
        embed = discord.Embed(
            title="Mon compte Akasha",
            description="Consulte tes informations, tes statistiques et tes préférences avec les boutons ci-dessous.",
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed, view=AccountPanel(self))

    async def build_embed(self, discord_id):
        user = await self.db.get_user_by_discord_id(str(discord_id))
        embed = discord.Embed(title="Mon compte Akasha", color=discord.Color.blue())
        if not user:
            embed.description = "Ton compte n'est pas encore lié à Seerr. Utilise #verification pour le lier."
            return embed

        requests = await self._request_stats(user.get("overseerr_id"))
        problems = await self.db.get_problem_report_counts(str(discord_id))
        expires = user.get("wizarr_invite_expires")
        days = self._days_remaining(expires)
        embed.add_field(name="Date d'inscription", value=self._format_date(user.get("created_at")), inline=True)
        embed.add_field(name="Première inscription", value=self._format_date(user.get("created_at")), inline=True)
        embed.add_field(name="Expiration", value=self._format_date(expires), inline=True)
        embed.add_field(name="Jours restants", value=str(days) if days is not None else "Illimité / inconnue", inline=True)
        embed.add_field(name="Demandes", value=str(requests["total"]), inline=True)
        embed.add_field(name="Demandes disponibles", value=str(requests["available"]), inline=True)
        embed.add_field(name="Problèmes signalés", value=str(problems["total"]), inline=True)
        embed.add_field(name="Problèmes en attente", value=str(problems["open"]), inline=True)
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
