import os
import aiohttp


class TautulliClient:
    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or os.getenv("TAUTULLI_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("TAUTULLI_API_KEY", "")
        self._session = None

    @property
    def configured(self):
        return bool(self.base_url and self.api_key)

    async def _request(self, command, **params):
        if not self.configured:
            return {}
        if self._session is None:
            self._session = aiohttp.ClientSession()
        query = {"apikey": self.api_key, "cmd": command, **params}
        async with self._session.get(f"{self.base_url}/api/v2", params=query) as response:
            response.raise_for_status()
            payload = await response.json()
        return (payload.get("response") or {}).get("data") or {}

    async def get_user_statistics_by_email(self, email):
        if not email or not self.configured:
            return None
        users = await self._request("get_users_table", length=1000, start=0)
        rows = users.get("data") or []
        user = next((row for row in rows if (row.get("email") or "").lower().strip() == email.lower().strip()), None)
        if not user:
            return None
        details = await self._request("get_user", user_id=user.get("user_id"))
        return self._normalize_statistics({**user, **details})

    @staticmethod
    def _normalize_statistics(data):
        movies = int(data.get("movie_count") or data.get("movies_watched") or 0)
        episodes = int(data.get("episode_count") or data.get("episodes_watched") or 0)
        total_seconds = int(data.get("total_time") or data.get("duration") or 0)
        return {"movies": movies, "episodes": episodes, "total_seconds": total_seconds}

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
