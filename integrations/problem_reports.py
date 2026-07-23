import datetime
import logging
import os
import discord
from discord import ui
from integrations.plex_reports_client import PlexReportsClient

logger = logging.getLogger(__name__)

CATEGORIES = {
    "video": "Vidéo", "audio": "Audio", "subtitle": "Sous-titre", "account": "Compte",
    "playback": "Lecture / performances", "content": "Contenu",
}
SUBCATEGORIES = {
    "account": ["Renouvellement", "Abonnement", "Changement d'adresse e-mail", "Accès Plex", "Accès Seerr", "Accès Plex/Jellyfin"],
    "playback": ["Mauvaise qualité", "Lecture intermittente", "Paramétrage audio", "Paramétrage vidéo", "Application"],
}

class DescriptionModal(ui.Modal, title="Décrire le problème"):
    description = ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=1500)
    def __init__(self, flow, data):
        super().__init__()
        self.flow, self.data = flow, data
    async def on_submit(self, interaction):
        self.data["description"] = str(self.description).strip()
        await self.flow.submit(interaction, self.data)

class TitleModal(ui.Modal, title="Rechercher un contenu"):
    title_input = ui.TextInput(label="Titre du film ou de la série", max_length=150)
    def __init__(self, flow, data):
        super().__init__()
        self.flow, self.data = flow, data
    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await self.flow.search(str(self.title_input).strip(), self.data["media_type"])
        if not results:
            await interaction.followup.send("Aucun résultat. Vérifie le titre puis réessaie.", ephemeral=True)
            return
        await interaction.followup.send("Choisis le contenu :", view=MediaView(self.flow, self.data, results), ephemeral=True)

class CategorySelect(ui.Select):
    def __init__(self, flow):
        super().__init__(placeholder="Choisir le type de problème", options=[discord.SelectOption(label=v, value=k) for k,v in CATEGORIES.items()])
        self.flow = flow
    async def callback(self, interaction):
        category = self.values[0]
        data = {"category": category}
        if category in SUBCATEGORIES:
            await interaction.response.edit_message(content="Choisis une sous-catégorie :", view=SubcategoryView(self.flow, data))
        elif category in ("video", "audio", "subtitle"):
            await interaction.response.edit_message(content="Ce problème concerne :", view=MediaTypeView(self.flow, data))
        else:
            await interaction.response.send_modal(DescriptionModal(self.flow, data))

class CategoryView(ui.View):
    def __init__(self, flow):
        super().__init__(timeout=300); self.add_item(CategorySelect(flow))

class SubcategorySelect(ui.Select):
    def __init__(self, flow, data):
        super().__init__(placeholder="Choisir la sous-catégorie", options=[discord.SelectOption(label=x, value=x) for x in SUBCATEGORIES[data["category"]]])
        self.flow, self.data = flow, data
    async def callback(self, interaction):
        self.data["subcategory"] = self.values[0]
        await interaction.response.send_modal(DescriptionModal(self.flow, self.data))
class SubcategoryView(ui.View):
    def __init__(self, flow, data): super().__init__(timeout=300); self.add_item(SubcategorySelect(flow, data))

class MediaTypeView(ui.View):
    def __init__(self, flow, data): super().__init__(timeout=300); self.flow,self.data=flow,data
    @ui.button(label="Film", style=discord.ButtonStyle.primary)
    async def movie(self, interaction, button):
        self.data["media_type"]="movie"; await interaction.response.send_modal(TitleModal(self.flow,self.data))
    @ui.button(label="Série", style=discord.ButtonStyle.primary)
    async def tv(self, interaction, button):
        self.data["media_type"]="tv"; await interaction.response.send_modal(TitleModal(self.flow,self.data))

class MediaSelect(ui.Select):
    def __init__(self, flow, data, results, page):
        self.flow,self.data,self.results=flow,data,results
        start = page * 25
        options=[discord.SelectOption(label=(r.get("title") or r.get("name") or "Sans titre")[:100], value=str(i), description=str(r.get("releaseDate") or r.get("firstAirDate") or "")[:100]) for i,r in enumerate(results[start:start + 25], start=start)]
        super().__init__(placeholder="Choisir le contenu", options=options)
    async def callback(self, interaction):
        media=self.results[int(self.values[0])]; self.data.update(media_id=media.get("id"),media_title=media.get("title") or media.get("name"))
        if self.data["media_type"] == "tv":
            seasons=await self.flow.seasons(media.get("id")); await interaction.response.edit_message(content="Choisis la saison :",view=SeasonView(self.flow,self.data,seasons))
        else: await interaction.response.send_modal(DescriptionModal(self.flow,self.data))
class MediaView(ui.View):
    def __init__(self, flow,data,results,page=0):
        super().__init__(timeout=300); self.flow,self.data,self.results,self.page=flow,data,results,page
        self.add_item(MediaSelect(flow,data,results,page))
        if page:
            previous=ui.Button(label="Précédent",style=discord.ButtonStyle.secondary)
            previous.callback=self.previous; self.add_item(previous)
        if (page + 1) * 25 < len(results):
            following=ui.Button(label="Suivant",style=discord.ButtonStyle.secondary)
            following.callback=self.next; self.add_item(following)
    async def previous(self,interaction):
        await interaction.response.edit_message(view=MediaView(self.flow,self.data,self.results,self.page-1))
    async def next(self,interaction):
        await interaction.response.edit_message(view=MediaView(self.flow,self.data,self.results,self.page+1))

class SeasonSelect(ui.Select):
    def __init__(self, flow,data,seasons,page):
        self.flow,self.data,self.seasons=flow,data,seasons
        start = page * 24
        options = ([discord.SelectOption(label="Toutes les saisons",value="all")] if page == 0 else [])
        options += [discord.SelectOption(label=s.get("name") or f"Saison {s.get('seasonNumber')}",value=str(s.get("seasonNumber"))) for s in seasons[start:start + (24 if page == 0 else 25)]]
        super().__init__(placeholder="Choisir la saison",options=options)
    async def callback(self,interaction):
        if self.values[0]=="all": await interaction.response.send_modal(DescriptionModal(self.flow,self.data)); return
        self.data["season_number"]=int(self.values[0]); episodes=await self.flow.episodes(self.data["media_id"],self.data["season_number"]); await interaction.response.edit_message(content="Choisis l'épisode :",view=EpisodeView(self.flow,self.data,episodes))
class SeasonView(ui.View):
    def __init__(self,flow,data,seasons,page=0):
        super().__init__(timeout=300); self.flow,self.data,self.seasons,self.page=flow,data,seasons,page; self.add_item(SeasonSelect(flow,data,seasons,page))
        if page:
            button=ui.Button(label="Précédent",style=discord.ButtonStyle.secondary); button.callback=self.previous; self.add_item(button)
        if (page + 1) * 24 < len(seasons):
            button=ui.Button(label="Suivant",style=discord.ButtonStyle.secondary); button.callback=self.next; self.add_item(button)
    async def previous(self,interaction): await interaction.response.edit_message(view=SeasonView(self.flow,self.data,self.seasons,self.page-1))
    async def next(self,interaction): await interaction.response.edit_message(view=SeasonView(self.flow,self.data,self.seasons,self.page+1))
class EpisodeSelect(ui.Select):
    def __init__(self,flow,data,episodes,page):
        self.flow,self.data,self.episodes=flow,data,episodes
        start = page * 24
        options = ([discord.SelectOption(label="Tous les épisodes",value="all")] if page == 0 else [])
        options += [discord.SelectOption(label=f"E{e.get('episodeNumber')} — {e.get('name')}",value=str(i)) for i,e in enumerate(episodes[start:start + (24 if page == 0 else 25)], start=start)]
        super().__init__(placeholder="Choisir l'épisode",options=options)
    async def callback(self,interaction):
        if self.values[0]!="all":
            episode=self.episodes[int(self.values[0])]; self.data.update(episode_number=episode.get("episodeNumber"),episode_title=episode.get("name"))
        await interaction.response.send_modal(DescriptionModal(self.flow,self.data))
class EpisodeView(ui.View):
    def __init__(self,flow,data,episodes,page=0):
        super().__init__(timeout=300); self.flow,self.data,self.episodes,self.page=flow,data,episodes,page; self.add_item(EpisodeSelect(flow,data,episodes,page))
        if page:
            button=ui.Button(label="Précédent",style=discord.ButtonStyle.secondary); button.callback=self.previous; self.add_item(button)
        if (page + 1) * 24 < len(episodes):
            button=ui.Button(label="Suivant",style=discord.ButtonStyle.secondary); button.callback=self.next; self.add_item(button)
    async def previous(self,interaction): await interaction.response.edit_message(view=EpisodeView(self.flow,self.data,self.episodes,self.page-1))
    async def next(self,interaction): await interaction.response.edit_message(view=EpisodeView(self.flow,self.data,self.episodes,self.page+1))

class MemberFollowupModal(ui.Modal, title="Ajouter une précision"):
    message = ui.TextInput(label="Précision", style=discord.TextStyle.paragraph, max_length=1500)
    def __init__(self, flow, report_id):
        super().__init__(); self.flow, self.report_id = flow, report_id
    async def on_submit(self, interaction):
        report = await self.flow.db.get_problem_report(self.report_id)
        description = f"{report['description']}\n\nPrécision du membre : {self.message}"
        await self.flow.db.update_problem_report(self.report_id, description=description)
        await interaction.response.send_message("Précision ajoutée au signalement.", ephemeral=True)

class MemberReportView(ui.View):
    def __init__(self, flow, report):
        super().__init__(timeout=300); self.flow, self.report = flow, report
        source = report.get("source") or "discord"
        if source == "seerr" and report.get("external_id"):
            self.add_item(ui.Button(label="Ouvrir dans Seerr", style=discord.ButtonStyle.link, url=f"{os.getenv('OVERSEERR_BASE_URL', '').rstrip('/')}/issues/{report['external_id']}"))
        if source == "plex" and report.get("media_title", "").startswith("http"):
            self.add_item(ui.Button(label="Ouvrir dans Plex", style=discord.ButtonStyle.link, url=report["media_title"]))
        if source == "discord" and report.get("status") == "open":
            button = ui.Button(label="Répondre", style=discord.ButtonStyle.primary)
            button.callback = self.followup; self.add_item(button)
    async def followup(self, interaction):
        await interaction.response.send_modal(MemberFollowupModal(self.flow, self.report["id"]))

class ReportPanel(ui.View):
    def __init__(self,flow): super().__init__(timeout=None); self.flow=flow
    @ui.button(label="Signaler un problème",style=discord.ButtonStyle.danger,custom_id="report:start")
    async def start(self,interaction,button): await interaction.response.send_message("Quel problème veux-tu signaler ?",view=CategoryView(self.flow),ephemeral=True)
    @ui.button(label="Mes signalements",style=discord.ButtonStyle.secondary,custom_id="report:list")
    async def list(self,interaction,button):
        reports=await self.flow.db.get_problem_reports_for_user(str(interaction.user.id))
        if not reports:
            await interaction.response.send_message("Aucun signalement.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self.flow.embed(reports[0]), view=MemberReportView(self.flow, reports[0]), ephemeral=True)
        for report in reports[1:10]:
            await interaction.followup.send(embed=self.flow.embed(report), view=MemberReportView(self.flow, report), ephemeral=True)

class AdminReportDashboard(ui.View):
    def __init__(self, flow, status=None):
        super().__init__(timeout=None)
        self.flow, self.status = flow, status
        for label, value, custom_id in (
            ("Tous", None, "report:admin:all"),
            ("Ouverts", "open", "report:admin:open"),
            ("Fermés", "closed", "report:admin:closed"),
        ):
            button = ui.Button(
                label=label,
                style=discord.ButtonStyle.primary if value == status else discord.ButtonStyle.secondary,
                custom_id=custom_id,
            )
            button.callback = self._callback(value)
            self.add_item(button)

    def _callback(self, status):
        async def callback(interaction):
            await self._show(interaction, status)
        return callback

    async def _show(self, interaction, status):
        if interaction.user.id != self.flow.admin_id:
            await interaction.response.send_message("Réservé à l'administrateur.", ephemeral=True)
            return
        reports = list(reversed(await self.flow.db.get_problem_reports(status)))
        label = "Tous" if status is None else ("Ouverts" if status == "open" else "Fermés")
        await interaction.response.edit_message(
            content=f"{len(reports)} signalement(s) — {label}",
            embeds=[self.flow.embed(report) for report in reports[:10]],
            view=AdminReportDashboard(self.flow, status),
        )

class AdminView(ui.View):
    def __init__(self,flow,report_id):
        super().__init__(timeout=None); self.flow,self.report_id=flow,report_id
        reply=ui.Button(label="Répondre",style=discord.ButtonStyle.primary,custom_id=f"report:{report_id}:reply")
        resolve=ui.Button(label="Marquer comme résolu",style=discord.ButtonStyle.success,custom_id=f"report:{report_id}:resolve")
        reply.callback=self.reply; resolve.callback=self.resolve
        self.add_item(reply); self.add_item(resolve)
    async def reply(self,interaction):
        if interaction.user.id!=self.flow.admin_id: await interaction.response.send_message("Réservé à l'administrateur.",ephemeral=True); return
        await interaction.response.send_modal(AdminReplyModal(self.flow,self.report_id))
    async def resolve(self,interaction): await self.flow.resolve(interaction,self.report_id)
class ReopenView(ui.View):
    def __init__(self, flow, report_id):
        super().__init__(timeout=None); self.flow, self.report_id = flow, report_id
        button = ui.Button(label="Rouvrir", style=discord.ButtonStyle.secondary, custom_id=f"report:{report_id}:reopen")
        button.callback = self.reopen; self.add_item(button)
    async def reopen(self, interaction):
        await self.flow.reopen(interaction, self.report_id)

class AdminReplyModal(ui.Modal,title="Répondre au signalement"):
    response_text=ui.TextInput(label="Réponse",style=discord.TextStyle.paragraph,max_length=1500)
    def __init__(self,flow,report_id): super().__init__(); self.flow,self.report_id=flow,report_id
    async def on_submit(self,interaction): await self.flow.reply(interaction,self.report_id,str(self.response_text))

class ProblemReportFlow:
    def __init__(self,bridge,db,overseerr):
        self.bridge,self.db,self.overseerr=bridge,db,overseerr
        self.admin_id=bridge.admin_id
        self.plex_reports=PlexReportsClient()
    async def register(self,bot):
        bot.add_view(ReportPanel(self))
        bot.add_view(AdminReportDashboard(self))
        for report in await self.db.get_open_problem_reports():
            bot.add_view(AdminView(self,report["id"]),message_id=report.get("admin_message_id"))
        for report in await self.db.get_problem_reports("closed"):
            if report.get("admin_message_id"):
                bot.add_view(ReopenView(self,report["id"]),message_id=report["admin_message_id"])
    async def _find_admin_dashboard(self, channel):
        async for message in channel.history(limit=100):
            for row in message.components:
                for component in row.children:
                    if (component.custom_id or "").startswith("report:admin:"):
                        return message
        return None

    async def publish_admin_report(self, guild, report_id):
        report = await self.db.get_problem_report(report_id)
        channel = await self.ensure_admin_channel(guild)
        dashboard = await self._find_admin_dashboard(channel)
        if dashboard:
            await dashboard.delete()
        message = await channel.send(embed=self.embed(report), view=AdminView(self, report_id))
        await self.db.update_problem_report(report_id, admin_message_id=message.id, admin_channel_id=channel.id)
        await channel.send("Tableau des signalements :", view=AdminReportDashboard(self))
        return message

    async def sync_plex_reports(self, guild=None):
        if not self.plex_reports.token:
            return 0
        guild = guild or self.bridge.bot.get_guild(self.bridge.guild_id)
        imported = 0
        after = None
        while True:
            page = await self.plex_reports.list_reports(first=100, after=after)
            for report in page.get("nodes", []):
                if await self.db.get_problem_report_by_external_id("plex", report["id"]):
                    continue
                author = report.get("user") or {}
                user = await self.db.get_user_by_plex_username(author.get("username") or author.get("displayName") or "")
                if not user:
                    continue
                report_id = await self.db.create_problem_report(
                    discord_id=user["discord_id"],
                    discord_username=user.get("discord_username") or author.get("displayName") or author.get("username") or "Plex",
                    category="content",
                    subcategory="Plex",
                    media_type=None,
                    media_id=None,
                    media_title=report.get("url"),
                    season_number=None,
                    episode_number=None,
                    episode_title=None,
                    description=report.get("message") or "Signalement Plex",
                    reported_at=report.get("date") or datetime.datetime.utcnow().isoformat(),
                    source="plex",
                    external_id=report["id"],
                )
                if guild:
                    await self.publish_admin_report(guild, report_id)
                imported += 1
            page_info = page.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                return imported
            after = page_info.get("endCursor")

    async def sync_seerr_issues(self, guild=None):
        guild = guild or self.bridge.bot.get_guild(self.bridge.guild_id)
        if not self.overseerr:
            return 0
        imported = 0
        page_number = 1
        while True:
            page = await self.overseerr.get_issues(page=page_number, limit=20)
            for issue in page.get("results", []):
                external_id = str(issue.get("id"))
                if not external_id or await self.db.get_problem_report_by_external_id("seerr", external_id):
                    continue
                creator = issue.get("createdBy") or {}
                settings = creator.get("settings") or {}
                discord_ids = settings.get("discordIds") or ([settings["discordId"]] if settings.get("discordId") else [])
                user = None
                if discord_ids:
                    user = await self.db.get_user_by_discord_id(str(discord_ids[0]))
                if user is None and creator.get("id") is not None:
                    user = await self.db.get_user_by_overseerr_id(creator["id"])
                if not user:
                    continue
                media = issue.get("media") or {}
                report_id = await self.db.create_problem_report(
                    discord_id=user["discord_id"],
                    discord_username=user.get("discord_username") or creator.get("displayName") or creator.get("username") or "Seerr",
                    category="content",
                    subcategory="Seerr",
                    media_type=media.get("mediaType"),
                    media_id=media.get("tmdbId") or media.get("id"),
                    media_title=media.get("title") or media.get("name"),
                    season_number=None,
                    episode_number=None,
                    episode_title=None,
                    description=issue.get("description") or issue.get("comment") or "Signalement Seerr",
                    reported_at=issue.get("createdAt") or datetime.datetime.utcnow().isoformat(),
                    source="seerr",
                    external_id=external_id,
                )
                if guild:
                    await self.publish_admin_report(guild, report_id)
                imported += 1
            page_info = page.get("pageInfo") or {}
            if page_number >= page_info.get("pages", 1):
                return imported
            page_number += 1
    async def search(self,q,typ): return [r for r in (await self.overseerr.search_media(q)).get("results",[]) if r.get("mediaType")==typ]
    async def seasons(self,id): return (await self.overseerr.get_tv_details(id)).get("seasons",[])
    async def episodes(self,id,season): return (await self.overseerr.get_tv_season(id,season)).get("episodes",[])
    async def submit(self,interaction,data):
        report_id=await self.db.create_problem_report(discord_id=str(interaction.user.id),discord_username=interaction.user.name,description=data.pop("description"),reported_at=datetime.datetime.utcnow().isoformat(),**data)
        report=await self.db.get_problem_report(report_id)
        channel=await self.ensure_admin_channel(interaction.guild); embed=self.embed(report); message=await channel.send(embed=embed,view=AdminView(self,report_id)); await self.db.update_problem_report(report_id,admin_message_id=message.id,admin_channel_id=channel.id)
        try:
            await (await self.bridge.bot.fetch_user(self.admin_id)).send(f"Nouveau signalement #{report_id} de {interaction.user.mention}.")
        except discord.Forbidden:
            logger.warning("Cannot notify admin about report %s", report_id)
        await interaction.response.send_message(f"Signalement `#{report_id}` envoyé.",ephemeral=True)
    @staticmethod
    def _format_date(value):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%y")
        except (AttributeError, TypeError, ValueError):
            return value or "Inconnue"

    def embed(self,r):
        e=discord.Embed(title=f"{'✅ Résolu' if r['status']=='resolved' else '🆕 Signalement'} #{r['id']}",color=discord.Color.green() if r['status']=='resolved' else discord.Color.orange()); e.add_field(name="Utilisateur",value=f"<@{r['discord_id']}>",inline=True); e.add_field(name="Type",value=CATEGORIES[r['category']],inline=True); e.add_field(name="Source",value=(r.get("source") or "discord").title(),inline=True); e.add_field(name="Signalé",value=self._format_date(r.get("reported_at")),inline=False)
        e.add_field(name="Description du problème",value=(r.get("description") or "Aucune description.")[:1024],inline=False)
        if r.get('subcategory'): e.add_field(name="Sous-type",value=r['subcategory'],inline=True)
        if r.get('media_title'): e.add_field(name="Média",value=r['media_title'],inline=False)
        if r.get('admin_response'): e.add_field(name="Réponse",value=r['admin_response'],inline=False)
        if r.get('resolved_at'):
            resolved_by = f" par <@{r['admin_id']}>" if r.get("admin_id") else ""
            e.add_field(name="Résolu",value=f"{self._format_date(r['resolved_at'])}{resolved_by}",inline=False)
        return e
    async def reply(self,interaction,id,text):
        r=await self.db.get_problem_report(id)
        if r.get("source") == "plex" and r.get("external_id"):
            await self.plex_reports.create_comment(r["external_id"], text)
        elif r.get("source") == "seerr" and r.get("external_id") and self.overseerr:
            await self.overseerr.comment_issue(r["external_id"], text)
        await self.db.update_problem_report(id,admin_response=text,admin_id=str(interaction.user.id))
        try:
            await (await self.bridge.bot.fetch_user(int(r['discord_id']))).send(f"Réponse à ton signalement #{id} :\n{text}")
        except discord.Forbidden:
            logger.warning("Cannot notify member about reply to report %s", id)
        await interaction.response.send_message("Réponse envoyée.",ephemeral=True)
    async def resolve(self,interaction,id):
        if interaction.user.id!=self.admin_id: await interaction.response.send_message("Réservé à l'administrateur.",ephemeral=True); return
        r=await self.db.get_problem_report(id)
        if r.get("source") == "seerr" and r.get("external_id") and self.overseerr:
            await self.overseerr.update_issue_status(r["external_id"], "resolved")
        await self.db.update_problem_report(id,status="resolved",resolved_at=datetime.datetime.utcnow().isoformat(),admin_id=str(interaction.user.id))
        r=await self.db.get_problem_report(id)
        await interaction.message.edit(embed=self.embed(r),view=ReopenView(self, id))
        try:
            await (await self.bridge.bot.fetch_user(int(r['discord_id']))).send(f"Ton signalement #{id} a été marqué comme résolu.")
        except discord.Forbidden:
            logger.warning("Cannot notify member about resolution of report %s", id)
        await interaction.response.send_message("Signalement résolu.",ephemeral=True)
    async def reopen(self, interaction, id):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Réservé à l'administrateur.", ephemeral=True)
            return
        report = await self.db.get_problem_report(id)
        if report.get("source") == "seerr" and report.get("external_id") and self.overseerr:
            await self.overseerr.update_issue_status(report["external_id"], "open")
        await self.db.update_problem_report(id, status="open", resolved_at=None, admin_id=str(interaction.user.id))
        report = await self.db.get_problem_report(id)
        await interaction.message.edit(embed=self.embed(report), view=AdminView(self, id))
        try:
            await (await self.bridge.bot.fetch_user(int(report["discord_id"]))).send(f"Ton signalement #{id} a été rouvert.")
        except discord.Forbidden:
            logger.warning("Cannot notify member about reopening report %s", id)
        await interaction.response.send_message("Signalement rouvert.", ephemeral=True)
    async def ensure_member_channel(self,guild):
        subscriber=discord.utils.get(guild.roles,name=os.getenv("MEMBER_ROLE_NAME","Abonné")); trial=discord.utils.get(guild.roles,name=os.getenv("TRIAL_ROLE_NAME","Essai"))
        overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False)}
        for role in (subscriber,trial):
            if role: overwrites[role]=discord.PermissionOverwrite(view_channel=True,read_message_history=True,send_messages=False)
        channel=discord.utils.get(guild.text_channels,name="signaler")
        if channel is None:
            channel=await guild.create_text_channel("signaler",overwrites=overwrites,reason="Akasha problem reports")
        else: await channel.edit(overwrites=overwrites,reason="Managed by Akasha problem reports")
        async for message in channel.history(limit=30):
            if message.author.id==self.bridge.bot.user.id and message.components:
                return channel
        embed=discord.Embed(title="Signaler un problème",description="Utilise le bouton ci-dessous pour signaler un souci Plex, Seerr ou de lecture. Tes informations restent privées.",color=discord.Color.orange())
        await channel.send(embed=embed,view=ReportPanel(self)); return channel
    async def ensure_admin_channel(self,guild):
        category=discord.utils.get(guild.categories,name="Administration") or await guild.create_category("Administration")
        channel=discord.utils.get(category.text_channels,name="signalements")
        overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False)}
        admin_member=guild.get_member(self.admin_id)
        if admin_member:
            overwrites[admin_member]=discord.PermissionOverwrite(view_channel=True,read_message_history=True,send_messages=True)
        if channel is None:
            channel=await guild.create_text_channel("signalements",category=category,overwrites=overwrites,reason="Akasha problem reports")
        else:
            await channel.edit(overwrites=overwrites,reason="Managed by Akasha problem reports")
        if await self._find_admin_dashboard(channel):
            return channel
        await channel.send("Tableau des signalements :",view=AdminReportDashboard(self))
        return channel
