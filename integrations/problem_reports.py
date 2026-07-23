import datetime
import logging
import os
import discord
from discord import ui

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
    def __init__(self, flow, data, results):
        self.flow,self.data,self.results=flow,data,results
        options=[discord.SelectOption(label=(r.get("title") or r.get("name") or "Sans titre")[:100], value=str(i), description=str(r.get("releaseDate") or r.get("firstAirDate") or "")[:100]) for i,r in enumerate(results[:25])]
        super().__init__(placeholder="Choisir le contenu", options=options)
    async def callback(self, interaction):
        media=self.results[int(self.values[0])]; self.data.update(media_id=media.get("id"),media_title=media.get("title") or media.get("name"))
        if self.data["media_type"] == "tv":
            seasons=await self.flow.seasons(media.get("id")); await interaction.response.edit_message(content="Choisis la saison :",view=SeasonView(self.flow,self.data,seasons))
        else: await interaction.response.send_modal(DescriptionModal(self.flow,self.data))
class MediaView(ui.View):
    def __init__(self, flow,data,results): super().__init__(timeout=300); self.add_item(MediaSelect(flow,data,results))

class SeasonSelect(ui.Select):
    def __init__(self, flow,data,seasons):
        self.flow,self.data,self.seasons=flow,data,seasons
        super().__init__(placeholder="Choisir la saison",options=[discord.SelectOption(label=f"Toutes les saisons",value="all")]+[discord.SelectOption(label=s.get("name") or f"Saison {s.get('seasonNumber')}",value=str(s.get("seasonNumber"))) for s in seasons[:24]])
    async def callback(self,interaction):
        if self.values[0]=="all": await interaction.response.send_modal(DescriptionModal(self.flow,self.data)); return
        self.data["season_number"]=int(self.values[0]); episodes=await self.flow.episodes(self.data["media_id"],self.data["season_number"]); await interaction.response.edit_message(content="Choisis l'épisode :",view=EpisodeView(self.flow,self.data,episodes))
class SeasonView(ui.View):
    def __init__(self,flow,data,seasons): super().__init__(timeout=300); self.add_item(SeasonSelect(flow,data,seasons))
class EpisodeSelect(ui.Select):
    def __init__(self,flow,data,episodes):
        self.flow,self.data,self.episodes=flow,data,episodes
        super().__init__(placeholder="Choisir l'épisode",options=[discord.SelectOption(label="Tous les épisodes",value="all")]+[discord.SelectOption(label=f"E{e.get('episodeNumber')} — {e.get('name')}",value=str(i)) for i,e in enumerate(episodes[:24])])
    async def callback(self,interaction):
        if self.values[0]!="all":
            episode=self.episodes[int(self.values[0])]; self.data.update(episode_number=episode.get("episodeNumber"),episode_title=episode.get("name"))
        await interaction.response.send_modal(DescriptionModal(self.flow,self.data))
class EpisodeView(ui.View):
    def __init__(self,flow,data,episodes): super().__init__(timeout=300); self.add_item(EpisodeSelect(flow,data,episodes))

class ReportPanel(ui.View):
    def __init__(self,flow): super().__init__(timeout=None); self.flow=flow
    @ui.button(label="Signaler un problème",style=discord.ButtonStyle.danger,custom_id="report:start")
    async def start(self,interaction,button): await interaction.response.send_message("Quel problème veux-tu signaler ?",view=CategoryView(self.flow),ephemeral=True)
    @ui.button(label="Mes signalements",style=discord.ButtonStyle.secondary,custom_id="report:list")
    async def list(self,interaction,button):
        reports=await self.flow.db.get_problem_reports_for_user(str(interaction.user.id)); text="\n".join(f"`#{r['id']}` {CATEGORIES[r['category']]} — {'Résolu' if r['status']=='resolved' else 'Ouvert'}" for r in reports) or "Aucun signalement."
        await interaction.response.send_message(text,ephemeral=True)

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
class AdminReplyModal(ui.Modal,title="Répondre au signalement"):
    response_text=ui.TextInput(label="Réponse",style=discord.TextStyle.paragraph,max_length=1500)
    def __init__(self,flow,report_id): super().__init__(); self.flow,self.report_id=flow,report_id
    async def on_submit(self,interaction): await self.flow.reply(interaction,self.report_id,str(self.response_text))

class ProblemReportFlow:
    def __init__(self,bridge,db,overseerr): self.bridge,self.db,self.overseerr=bridge,db,overseerr; self.admin_id=bridge.admin_id
    async def register(self,bot):
        bot.add_view(ReportPanel(self))
        for report in await self.db.get_open_problem_reports():
            bot.add_view(AdminView(self,report["id"]),message_id=report.get("admin_message_id"))
    async def search(self,q,typ): return [r for r in (await self.overseerr.search_media(q)).get("results",[]) if r.get("mediaType")==typ]
    async def seasons(self,id): return (await self.overseerr.get_tv_details(id)).get("seasons",[])
    async def episodes(self,id,season): return (await self.overseerr.get_tv_season(id,season)).get("episodes",[])
    async def submit(self,interaction,data):
        report_id=await self.db.create_problem_report(discord_id=str(interaction.user.id),discord_username=interaction.user.name,description=data.pop("description"),reported_at=datetime.datetime.utcnow().isoformat(),**data)
        channel=await self.ensure_admin_channel(interaction.guild); embed=self.embed(await self.db.get_problem_report(report_id)); message=await channel.send(embed=embed,view=AdminView(self,report_id)); await self.db.update_problem_report(report_id,admin_message_id=message.id,admin_channel_id=channel.id); await interaction.response.send_message(f"Signalement `#{report_id}` envoyé.",ephemeral=True)
    def embed(self,r):
        e=discord.Embed(title=f"{'✅ Résolu' if r['status']=='resolved' else '🆕 Signalement'} #{r['id']}",description=r['description'],color=discord.Color.green() if r['status']=='resolved' else discord.Color.orange()); e.add_field(name="Utilisateur",value=f"<@{r['discord_id']}>",inline=True); e.add_field(name="Type",value=CATEGORIES[r['category']],inline=True); e.add_field(name="Signalé",value=r['reported_at'],inline=False)
        if r.get('media_title'): e.add_field(name="Média",value=r['media_title'],inline=False)
        if r.get('admin_response'): e.add_field(name="Réponse",value=r['admin_response'],inline=False)
        if r.get('resolved_at'): e.add_field(name="Résolu",value=r['resolved_at'],inline=False)
        return e
    async def reply(self,interaction,id,text):
        r=await self.db.get_problem_report(id); await self.db.update_problem_report(id,admin_response=text,admin_id=str(interaction.user.id)); await (await self.bridge.bot.fetch_user(int(r['discord_id']))).send(f"Réponse à ton signalement #{id} :\n{text}"); await interaction.response.send_message("Réponse envoyée en DM.",ephemeral=True)
    async def resolve(self,interaction,id):
        if interaction.user.id!=self.admin_id: await interaction.response.send_message("Réservé à l'administrateur.",ephemeral=True); return
        r=await self.db.get_problem_report(id); await self.db.update_problem_report(id,status="resolved",resolved_at=datetime.datetime.utcnow().isoformat(),admin_id=str(interaction.user.id)); r=await self.db.get_problem_report(id); await interaction.message.edit(embed=self.embed(r),view=None); await interaction.response.send_message("Signalement résolu.",ephemeral=True)
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
        category=discord.utils.get(guild.categories,name="Administration") or await guild.create_category("Administration"); channel=discord.utils.get(category.text_channels,name="signalements")
        if channel:return channel
        return await guild.create_text_channel("signalements",category=category,overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False)},reason="Akasha problem reports")
