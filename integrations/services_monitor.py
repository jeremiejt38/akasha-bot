"""Service status monitor for the Akasha admin panel."""
import os
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)


SERVICES = [
    {"name": "Plex", "url_env": "PLEX_URL", "health_path": "/", "type": "plex"},
    {"name": "Jellyfin", "url_env": "JELLYFIN_URL", "health_path": "/System/Info/Public", "type": "jellyfin"},
    {"name": "Overseerr", "url_env": "SEERR_URL", "health_path": "/api/v1/status", "type": "overseerr"},
    {"name": "Wizarr", "url_env": "WIZARR_BASE_URL", "health_path": "/api/status", "type": "wizarr"},
    {"name": "Site web", "url_env": "WEBSITE_URL", "health_path": "/", "type": "website"},
]


class ServicesMonitor:
    """Monitor Akasha services and build status embeds."""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def _fetch(self, url: str) -> dict:
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                data = {}
                try:
                    data = await resp.json()
                except Exception:
                    pass
                return {"ok": resp.status < 500, "status": resp.status, "data": data}
        except asyncio.TimeoutError:
            return {"ok": False, "status": "timeout", "data": {}}
        except Exception as e:
            return {"ok": False, "status": f"error: {type(e).__name__}", "data": {}}

    async def check_all(self) -> list[dict]:
        results = []
        for svc in SERVICES:
            base_url = os.getenv(svc["url_env"], "")
            if not base_url:
                results.append({"name": svc["name"], "ok": None, "status": "non configuré", "version": "N/A", "uptime": "N/A"})
                continue
            url = base_url.rstrip("/") + svc["health_path"]
            info = await self._fetch(url)
            version = "N/A"
            uptime = "N/A"

            data = info.get("data") or {}
            if svc["type"] == "jellyfin":
                version = data.get("Version") or version
            elif svc["type"] == "overseerr":
                version = data.get("version") or version
            elif svc["type"] == "wizarr":
                version = data.get("version") or version
            elif svc["type"] == "plex":
                version = data.get("MediaContainer", {}).get("version") or version

            results.append({
                "name": svc["name"],
                "ok": info["ok"],
                "status": info["status"],
                "version": version,
                "uptime": uptime,
            })
        return results

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
