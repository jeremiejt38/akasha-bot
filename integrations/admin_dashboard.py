"""Interactive admin dashboard for the Akasha Discord bot.

Provides an embed-based dashboard with navigation buttons so the admin can
switch between views without creating many channels.
"""
import os
import datetime
import logging
import discord
from discord import ui

logger = logging.getLogger(__name__)

TRUST_SCORE_LOW_THRESHOLD = float(os.getenv("TRUST_SCORE_LOW_THRESHOLD", "50"))
EXPIRATION_DAYS_WARNING = int(os.getenv("EXPIRATION_DAYS_WARNING", "7"))


class AdminDashboard:
    def __init__(self, discord_bridge, db, overseerr_client=None):
        self.discord_bridge = discord_bridge
        self.db = db
        self.overseerr_client = overseerr_client

    async def send_dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            embed = await self._build_overview_embed()
            view = AdminDashboardView(self)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Failed to send admin dashboard")
            await interaction.followup.send(
                "Impossible d'afficher le tableau de bord.", ephemeral=True
            )

    async def _get_users(self):
        return await self.db.get_all_users()

    def _format_date(self, date_str: str | None) -> str:
        if not date_str:
            return "Inconnue"
        try:
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return date_str

    def _now_utc(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    def _days_until(self, date_str: str | None) -> int | None:
        if not date_str:
            return None
        try:
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return int((dt - self._now_utc()).total_seconds() / 86400)
        except Exception:
            return None

    async def _build_overview_embed(self) -> discord.Embed:
        users = await self._get_users()
        total = len(users)
        expiring = sum(1 for u in users if (d := self._days_until(u.get("wizarr_invite_expires"))) is not None and d <= EXPIRATION_DAYS_WARNING)
        low_trust = [u for u in users if (u.get("tracearr_trust_score") or 100) < TRUST_SCORE_LOW_THRESHOLD]
        avg_trust = sum((u.get("tracearr_trust_score") or 0) for u in users) / total if total else 0

        embed = discord.Embed(
            title="Tableau de bord Akasha — Vue globale",
            color=discord.Color.blue(),
            timestamp=self._now_utc(),
        )
        embed.add_field(name="Abonnés totaux", value=str(total), inline=True)
        embed.add_field(name="Expirations ≤ 7 j", value=str(expiring), inline=True)
        embed.add_field(name="Trust score moyen", value=f"{avg_trust:.1f}", inline=True)
        embed.add_field(name="Trust score bas", value=str(len(low_trust)), inline=True)
        return embed

    async def _build_subscribers_embed(self, page: int = 0) -> discord.Embed:
        users = await self._get_users()
        per_page = 10
        start = page * per_page
        end = start + per_page
        page_users = users[start:end]

        embed = discord.Embed(
            title=f"Liste des abonnés (page {page + 1}/{(len(users) - 1) // per_page + 1 or 1})",
            color=discord.Color.green(),
        )

        if not page_users:
            embed.description = "Aucun abonné trouvé."
            return embed

        for u in page_users:
            name = f"<@{u.get('discord_id')}>"
            exp = self._format_date(u.get("wizarr_invite_expires"))
            created = self._format_date(u.get("created_at"))
            months = u.get("months_subscribed") or 0
            trust = u.get("tracearr_trust_score") or "N/A"
            notes = u.get("admin_notes")
            notes_line = f"Note admin: {notes}\n" if notes else ""
            value = (
                f"Email: {u.get('email') or 'N/A'}\n"
                f"Inscription: {created}\n"
                f"Expiration: {exp}\n"
                f"Mois cumulés: {months}\n"
                f"Trust score: {trust}\n"
                f"{notes_line}"
            )
            embed.add_field(name=name, value=value, inline=False)

        return embed

    async def _build_expirations_embed(self) -> discord.Embed:
        users = await self._get_users()
        soon = []
        for u in users:
            days = self._days_until(u.get("wizarr_invite_expires"))
            if days is not None and days <= EXPIRATION_DAYS_WARNING:
                soon.append((u, days))
        soon.sort(key=lambda x: x[1])

        embed = discord.Embed(
            title=f"Abonnés expirant dans ≤ {EXPIRATION_DAYS_WARNING} jours",
            color=discord.Color.gold(),
        )
        if not soon:
            embed.description = "Aucune expiration imminente."
            return embed

        for u, days in soon:
            name = f"<@{u.get('discord_id')}>"
            value = f"Expire dans **{days} jours** ({self._format_date(u.get('wizarr_invite_expires'))})"
            embed.add_field(name=name, value=value, inline=False)

        return embed

    async def _build_requests_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Demandes de contenu en attente",
            color=discord.Color.purple(),
        )
        if not self.overseerr_client:
            embed.description = "Overseerr n'est pas configuré."
            return embed

        try:
            # Pending requests count and first few
            pending_count = 0
            details = []
            page = 1
            while True:
                data = await self.overseerr_client._request("GET", "/request", params={"filter": "pending", "take": 100, "skip": (page - 1) * 100})
                results = data.get("results", [])
                if not results:
                    break
                pending_count += len(results)
                for req in results[:5] if not details else []:
                    title = req.get("media", {}).get("title") or req.get("media", {}).get("name") or "Inconnu"
                    requester = req.get("requestedBy", {}).get("displayName") or "Inconnu"
                    details.append(f"• **{title}** demandé par {requester}")
                if len(results) < 100:
                    break
                page += 1

            embed.add_field(name="Total en attente", value=str(pending_count), inline=True)
            if details:
                embed.add_field(name="Dernières demandes", value="\n".join(details), inline=False)
        except Exception:
            logger.exception("Failed to fetch pending requests")
            embed.description = "Impossible de récupérer les demandes Overseerr."

        return embed

    async def _build_low_trust_embed(self) -> discord.Embed:
        users = await self._get_users()
        low = [u for u in users if (u.get("tracearr_trust_score") or 100) < TRUST_SCORE_LOW_THRESHOLD]
        low.sort(key=lambda u: u.get("tracearr_trust_score", 0))

        embed = discord.Embed(
            title=f"Abonnés avec un trust score < {TRUST_SCORE_LOW_THRESHOLD}",
            color=discord.Color.red(),
        )
        if not low:
            embed.description = "Aucun abonné avec un trust score bas."
            return embed

        for u in low:
            name = f"<@{u.get('discord_id')}> — {u.get('tracearr_trust_score')}"
            violations = u.get("tracearr_total_violations") or 0
            value = f"Violations: {violations}"
            embed.add_field(name=name, value=value, inline=False)

        return embed

    async def _build_stats_embed(self) -> discord.Embed:
        users = await self._get_users()
        total = len(users)
        months = sum((u.get("months_subscribed") or 0) for u in users)
        avg_trust = sum((u.get("tracearr_trust_score") or 0) for u in users) / total if total else 0
        with_plex = sum(1 for u in users if u.get("overseerr_plex_username"))

        embed = discord.Embed(
            title="Statistiques Akasha",
            color=discord.Color.teal(),
        )
        embed.add_field(name="Abonnés totaux", value=str(total), inline=True)
        embed.add_field(name="Avec Plex lié", value=str(with_plex), inline=True)
        embed.add_field(name="Mois cumulés", value=str(months), inline=True)
        embed.add_field(name="Trust score moyen", value=f"{avg_trust:.1f}", inline=True)
        return embed


class AdminDashboardView(ui.View):
    def __init__(self, dashboard: AdminDashboard):
        super().__init__(timeout=300)
        self.dashboard = dashboard
        self.page = 0

    async def _update(self, interaction: discord.Interaction, embed: discord.Embed):
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Vue globale", style=discord.ButtonStyle.primary, emoji="📊")
    async def overview(self, interaction: discord.Interaction, _button: ui.Button):
        embed = await self.dashboard._build_overview_embed()
        await self._update(interaction, embed)

    @ui.button(label="Abonnés", style=discord.ButtonStyle.secondary, emoji="👥")
    async def subscribers(self, interaction: discord.Interaction, _button: ui.Button):
        embed = await self.dashboard._build_subscribers_embed(page=self.page)
        await self._update(interaction, embed)

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, _button: ui.Button):
        self.page = max(0, self.page - 1)
        embed = await self.dashboard._build_subscribers_embed(page=self.page)
        await self._update(interaction, embed)

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, _button: ui.Button):
        users = await self.dashboard._get_users()
        max_page = max(0, (len(users) - 1) // 10)
        self.page = min(max_page, self.page + 1)
        embed = await self.dashboard._build_subscribers_embed(page=self.page)
        await self._update(interaction, embed)

    @ui.button(label="Expirations", style=discord.ButtonStyle.secondary, emoji="⏳")
    async def expirations(self, interaction: discord.Interaction, _button: ui.Button):
        embed = await self.dashboard._build_expirations_embed()
        await self._update(interaction, embed)

    @ui.button(label="Demandes", style=discord.ButtonStyle.secondary, emoji="📥")
    async def requests(self, interaction: discord.Interaction, _button: ui.Button):
        embed = await self.dashboard._build_requests_embed()
        await self._update(interaction, embed)

    @ui.button(label="Trust bas", style=discord.ButtonStyle.secondary, emoji="⚠️")
    async def low_trust(self, interaction: discord.Interaction, _button: ui.Button):
        embed = await self.dashboard._build_low_trust_embed()
        await self._update(interaction, embed)

    @ui.button(label="Stats", style=discord.ButtonStyle.secondary, emoji="📈")
    async def stats(self, interaction: discord.Interaction, _button: ui.Button):
        embed = await self.dashboard._build_stats_embed()
        await self._update(interaction, embed)
