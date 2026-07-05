import os
import logging
from typing import List, Dict
import aiohttp

logger = logging.getLogger(__name__)

CONNECTION_CHECK_MARKER = "__HEALTH_CHECK__"


def _default_urls() -> List[Dict]:
    return [
        {"name": "Plex", "url": os.getenv("PLEX_URL", "https://plex.akasha.ing"), "ok_statuses": {401}},
        {"name": "Seerr", "url": os.getenv("SEERR_URL", "https://seerr.akasha.ing"), "ok_statuses": set()},
        {"name": "Inscriptions", "url": os.getenv("WIZARR_URL", os.getenv("WIZARR_BASE_URL", "https://eveil.akasha.ing")), "ok_statuses": set()},
        {"name": "JellyFin", "url": os.getenv("JELLYFIN_URL", "https://jelly.akasha.ing"), "ok_statuses": set()},
        {"name": "Site Web", "url": os.getenv("WEBSITE_URL", "https://akasha.ing"), "ok_statuses": set()},
    ]


class HealthChecker:
    """Check availability of Akasha services and format the results."""

    def __init__(self, urls: List[Dict] = None, timeout: float = 10):
        self.urls = urls or _default_urls()
        self.timeout = timeout

    async def check_all(self) -> List[Dict]:
        results = []
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for entry in self.urls:
                result = {
                    "name": entry["name"],
                    "url": entry["url"],
                    "ok": False,
                    "status": None,
                    "error": None,
                }
                try:
                    async with session.get(entry["url"], allow_redirects=True) as resp:
                        allowed = entry.get("ok_statuses", set())
                        result["ok"] = (200 <= resp.status < 300) or (resp.status in allowed)
                        result["status"] = resp.status
                except Exception as exc:
                    result["error"] = str(exc)
                results.append(result)
        return results

    def format_results(self, results: List[Dict]) -> str:
        lines = ["**État des services Akasha :**"]
        for r in results:
            if r["ok"]:
                lines.append(f"🟢 {r['name']} — {r['url']} (HTTP {r['status']})")
            else:
                detail = r["error"] or f"HTTP {r['status']}"
                lines.append(f"🔴 {r['name']} — {r['url']} ({detail})")
        return "\n".join(lines)
