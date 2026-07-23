import asyncio
import datetime
import logging
import os
from urllib.parse import quote

import aiohttp
import discord
from integrations.admin_access import ensure_admin_category_access

logger = logging.getLogger(__name__)

SERVICE_CONTAINERS = {
    "Plex": "plex",
    "Jellyfin": "Jellyfin",
    "Flaresolverr": "flaresolverr",
    "Prowlarr": "prowlarr",
    "Radarr": "radarr",
    "Sonarr": "sonarr",
    "Seerr": "Seerr",
    "Tautulli": "tautulli",
    "Tracearr": "tracearr-supervised",
    "Traefik": "traefik",
    "Wizarr": "Wizarr",
    "Linkstack": "linkstack",
    "Nginx": "nginx",
    "qBittorrent Radarr": "qbittorrent-radarr",
    "qBittorrent Sonarr": "qbittorrent-sonarr",
}

ALERTED_SERVICES = {"Plex", "Jellyfin", "Flaresolverr", "Prowlarr", "Radarr", "Sonarr", "Seerr", "Tautulli", "Tracearr", "Traefik", "Wizarr", "Linkstack", "Nginx", "qBittorrent Radarr", "qBittorrent Sonarr"}


class DockerServiceClient:
    def __init__(self, base_url=None):
        self.base_url = (base_url or os.getenv("DOCKER_API_URL", "http://172.22.0.2:2375")).rstrip("/")
        self.session = None
        self.update_cache = {}

    async def _get(self, path):
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        async with self.session.get(f"{self.base_url}{path}") as response:
            response.raise_for_status()
            return await response.json()

    async def statuses(self):
        containers = await self._get("/containers/json?all=1")
        by_name = {container["Names"][0].lstrip("/"): container for container in containers}
        results = []
        for service, container_name in SERVICE_CONTAINERS.items():
            container = by_name.get(container_name)
            if not container:
                results.append({"name": service, "running": False, "error": "Conteneur introuvable", "version": "N/A", "ip": "N/A", "ports": "N/A"})
                continue
            details = await self._get(f"/containers/{container['Id']}/json")
            state = details.get("State") or {}
            network = next(iter((details.get("NetworkSettings") or {}).get("Networks", {}).values()), {})
            ports = self._format_ports((details.get("NetworkSettings") or {}).get("Ports") or {})
            image = (details.get("Config") or {}).get("Image") or container.get("Image") or "N/A"
            image_info = await self._image_info(image)
            labels = ((image_info or {}).get("Config") or {}).get("Labels") or {}
            version = labels.get("org.opencontainers.image.version") or labels.get("build_version") or image.rsplit(":", 1)[-1]
            results.append({
                "name": service,
                "running": bool(state.get("Running")),
                "healthy": (state.get("Health") or {}).get("Status") != "unhealthy",
                "error": state.get("Error") or state.get("Status") or "Arrêté",
                "version": version,
                "image": image,
                "ip": network.get("IPAddress") or "N/A",
                "ports": ports,
                "started_at": state.get("StartedAt"),
                "update_available": await self._update_available(image, image_info),
            })
        return results

    async def _image_info(self, image):
        try:
            return await self._get(f"/images/{quote(image, safe='')}/json")
        except aiohttp.ClientResponseError as error:
            if error.status != 403:
                logger.warning("Unable to inspect image %s: %s", image, error.status)
            return None

    async def _update_available(self, image, image_info):
        cached = self.update_cache.get(image)
        now = datetime.datetime.now(datetime.timezone.utc)
        if cached and now - cached[0] < datetime.timedelta(minutes=15):
            return cached[1]
        if not image_info:
            return None
        local_digests = image_info.get("RepoDigests") or []
        try:
            distribution = await self._get(f"/distribution/{quote(image, safe='')}/json")
            remote_digest = (distribution.get("Descriptor") or {}).get("digest")
            value = bool(remote_digest and local_digests and all(not digest.endswith(remote_digest) for digest in local_digests))
        except aiohttp.ClientResponseError as error:
            value = None if error.status == 403 else False
        except Exception:
            logger.exception("Unable to check image update for %s", image)
            value = None
        self.update_cache[image] = (now, value)
        return value

    @staticmethod
    def _format_ports(ports):
        values = []
        for container_port, bindings in ports.items():
            if bindings:
                values.extend(f"{binding.get('HostPort')}→{container_port}" for binding in bindings)
            else:
                values.append(container_port)
        return ", ".join(values) or "N/A"

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None


class ContainerServicesMonitor:
    def __init__(self, bridge):
        self.bridge = bridge
        self.client = DockerServiceClient()
        self.task = None
        self.down_since = {}
        self.alerted = set()
        self.message_id = None
        self.channel_id = None

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        while not self.bridge._closed:
            try:
                await self.refresh()
            except Exception:
                logger.exception("Failed to refresh container services")
            await asyncio.sleep(30)

    async def refresh(self):
        guild = self.bridge.bot.get_guild(self.bridge.guild_id)
        if not guild:
            return
        statuses = await self.client.statuses()
        await self._notify_unavailable(statuses)
        channel = guild.get_channel(self.channel_id) if self.channel_id else None
        if channel is None:
            channel = await self.ensure_channel(guild)
        await self._update_dashboard(channel, statuses)

    async def ensure_channel(self, guild):
        category = await ensure_admin_category_access(guild, self.bridge.admin_id)
        channel = discord.utils.get(category.text_channels, name="services")
        if channel is None:
            channel = await guild.create_text_channel("services", category=category, reason="Akasha services monitor")
        self.channel_id = channel.id
        return channel

    async def _update_dashboard(self, channel, statuses):
        embed = self._embed(statuses)
        message = None
        if self.message_id:
            try:
                message = await channel.fetch_message(self.message_id)
            except discord.NotFound:
                self.message_id = None
        if message is None:
            async for candidate in channel.history(limit=20):
                if candidate.author.id == self.bridge.bot.user.id and candidate.embeds and candidate.embeds[0].title == "Services Akasha":
                    message = candidate
                    break
        if message:
            await message.edit(embed=embed)
            self.message_id = message.id
        else:
            message = await channel.send(embed=embed)
            self.message_id = message.id

    def _embed(self, statuses):
        color = discord.Color.green() if all(status["running"] and status.get("healthy", True) for status in statuses) else discord.Color.red()
        embed = discord.Embed(title="Services Akasha", color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        lines = []
        for status in statuses:
            if not status["running"] or not status.get("healthy", True):
                icon, state = "�", "Arrêté"
            elif status.get("update_available"):
                icon, state = "�", "MàJ dispo"
            else:
                icon, state = "�", "À jour" if status.get("update_available") is False else "Démarré"
            lines.append(f"{icon} **{status['name']}** · {state} · `{status['version']}`")
        embed.description = "\n".join(lines)
        embed.set_footer(text="État toutes les 30 s · mises à jour vérifiées toutes les 15 min")
        return embed

    async def _notify_unavailable(self, statuses):
        now = datetime.datetime.now(datetime.timezone.utc)
        for status in statuses:
            name = status["name"]
            unavailable = not status["running"] or not status.get("healthy", True)
            if not unavailable:
                self.down_since.pop(name, None)
                self.alerted.discard(name)
                continue
            self.down_since.setdefault(name, now)
            if name in ALERTED_SERVICES and name not in self.alerted and now - self.down_since[name] >= datetime.timedelta(minutes=2):
                admin = await self.bridge.bot.fetch_user(self.bridge.admin_id)
                await admin.send(f"🔴 {name} est indisponible depuis plus de 2 minutes : {status.get('error') or 'erreur inconnue'}")
                self.alerted.add(name)

    @staticmethod
    def _uptime(started_at):
        if not started_at or started_at.startswith("0001"):
            return "N/A"
        try:
            started = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            elapsed = datetime.datetime.now(datetime.timezone.utc) - started
            days, seconds = elapsed.days, elapsed.seconds
            hours, minutes = divmod(seconds // 60, 60)
            return f"{days} j {hours} h {minutes} min"
        except ValueError:
            return "N/A"

    async def close(self):
        if self.task:
            self.task.cancel()
        await self.client.close()
