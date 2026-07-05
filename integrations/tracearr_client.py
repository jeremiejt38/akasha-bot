import os
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)


class TracearrClient:
    """Async client for the Tracearr public REST API.

    Requires environment variables:
      - TRACEARR_BASE_URL (e.g. https://tracearr.drac-lab.fr)
      - TRACEARR_API_KEY
    """

    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or os.getenv("TRACEARR_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("TRACEARR_API_KEY", "")
        self._session: aiohttp.ClientSession | None = None

    async def _session_ctx(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, path: str, params=None):
        if not self.base_url or not self.api_key:
            raise RuntimeError("TRACEARR_BASE_URL and TRACEARR_API_KEY must be configured")
        url = f"{self.base_url}/api/v1/public{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        session = await self._session_ctx()
        async with session.request(method, url, headers=headers, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_users(self):
        return await self._request("GET", "/users")

    async def get_stats(self):
        return await self._request("GET", "/stats")

    async def find_user_by_username(self, username: str):
        username = username.lower().strip()
        data = await self.get_users()
        for user in data.get("data", []):
            if (user.get("username") or "").lower().strip() == username:
                return user
        return None

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


async def _main():
    import json

    client = TracearrClient()
    try:
        logger.info("Stats: %s", await client.get_stats())
        users = await client.get_users()
        logger.info("Users: %s", json.dumps(users, indent=2)[:1000])
    except Exception:
        logger.exception("Tracearr API check failed")
        raise
    finally:
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    asyncio.run(_main())
