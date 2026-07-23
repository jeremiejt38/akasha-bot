import os
import asyncio
import logging
from urllib.parse import urlencode, quote
import aiohttp

logger = logging.getLogger(__name__)


class OverseerrClient:
    """Async client for the Overseerr REST API.

    Requires environment variables:
      - OVERSEERR_BASE_URL (e.g. https://seerr.akasha.ing)
      - OVERSEERR_API_KEY

    OpenAPI spec: https://github.com/sct/overseerr/blob/develop/overseerr-api.yml
    """

    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or os.getenv("OVERSEERR_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("OVERSEERR_API_KEY", "")
        self._session: aiohttp.ClientSession | None = None

    async def _session_ctx(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, path: str, json=None, params=None):
        if not self.base_url or not self.api_key:
            raise RuntimeError("OVERSEERR_BASE_URL and OVERSEERR_API_KEY must be configured")
        url = f"{self.base_url}/api/v1{path}"
        if params:
            url = f"{url}?{urlencode(params, doseq=True, quote_via=quote)}"
        headers = {"X-Api-Key": self.api_key}
        if json is not None:
            headers["Content-Type"] = "application/json"
        session = await self._session_ctx()
        async with session.request(method, url, headers=headers, json=json) as resp:
            resp.raise_for_status()
            if resp.status == 204:
                return None
            return await resp.json()

    async def get_status(self):
        return await self._request("GET", "/status")

    async def get_users(self, page: int = 1, limit: int = 10):
        return await self._request(
            "GET",
            "/user",
            params={"take": limit, "skip": max(0, page - 1) * limit},
        )

    async def get_user(self, user_id: int):
        return await self._request("GET", f"/user/{user_id}")

    async def get_user_settings(self, user_id: int):
        return await self._request("GET", f"/user/{user_id}/settings/notifications")

    async def get_user_discord_ids(self, user_id: int):
        settings = await self.get_user_settings(user_id)
        discord_ids = settings.get("discordIds") or []
        singular_discord_id = settings.get("discordId")
        if singular_discord_id is not None and str(singular_discord_id) not in {str(value) for value in discord_ids}:
            discord_ids.append(singular_discord_id)
        return discord_ids

    async def find_user_by_discord_id(self, discord_id: str):
        page = 1
        while True:
            data = await self.get_users(page=page, limit=20)
            for user in data.get("results", []):
                discord_ids = await self.get_user_discord_ids(user.get("id"))
                if str(discord_id) in {str(value) for value in discord_ids}:
                    return user
            page_info = data.get("pageInfo", {})
            if page >= page_info.get("pages", 1):
                break
            page += 1
        return None

    async def find_user_by_email(self, email: str):
        email = email.lower().strip()
        page = 1
        while True:
            data = await self.get_users(page=page, limit=20)
            for user in data.get("results", []):
                if (user.get("email") or "").lower().strip() == email:
                    return user
            page_info = data.get("pageInfo", {})
            if page >= page_info.get("pages", 1):
                break
            page += 1
        return None

    async def get_issues(self, page: int = 1, limit: int = 20):
        return await self._request(
            "GET",
            "/issue",
            params={"take": limit, "skip": max(0, page - 1) * limit},
        )

    async def comment_issue(self, issue_id: int | str, message: str):
        return await self._request("POST", f"/issue/{issue_id}/comment", json={"message": message})

    async def update_issue_status(self, issue_id: int | str, status: str):
        return await self._request("POST", f"/issue/{issue_id}/{status}")

    async def search_media(self, query: str, page: int = 1, limit: int = 10):
        data = await self._request("GET", "/search", params={"query": query})
        if limit and isinstance(data.get("results"), list):
            data["results"] = data["results"][:limit]
        return data

    async def get_movie_details(self, media_id: int):
        return await self._request("GET", f"/movie/{media_id}")

    async def get_tv_details(self, media_id: int):
        return await self._request("GET", f"/tv/{media_id}")

    async def get_tv_season(self, media_id: int, season_number: int):
        return await self._request("GET", f"/tv/{media_id}/season/{season_number}")

    async def request_media(self, media_type: str, media_id: int, user_id: int):
        """Create a media request in Overseerr.

        media_type should be 'movie' or 'tv'.
        media_id is the TMDB id from a search result.
        """
        payload = {
            "mediaType": media_type,
            "mediaId": media_id,
            "userId": user_id,
        }
        return await self._request("POST", "/request", json=payload)

    async def update_user_discord_id(self, user_id: int, discord_id: str | None):
        """Update a user's Discord ID without overwriting other notification settings."""
        settings = await self.get_user_settings(user_id)
        payload = {
            "pgpKey": settings.get("pgpKey"),
            "discordId": str(discord_id) if discord_id else None,
            "pushbulletAccessToken": settings.get("pushbulletAccessToken"),
            "pushoverApplicationToken": settings.get("pushoverApplicationToken"),
            "pushoverUserKey": settings.get("pushoverUserKey"),
            "telegramChatId": settings.get("telegramChatId"),
            "telegramSendSilently": settings.get("telegramSendSilently"),
            "notificationTypes": settings.get("notificationTypes", {}),
        }
        # Ensure Discord notifications are enabled when an ID is set
        if discord_id:
            notification_types = payload["notificationTypes"] or {}
            if not notification_types.get("discord"):
                notification_types["discord"] = 2
            payload["notificationTypes"] = notification_types
        return await self._request("POST", f"/user/{user_id}/settings/notifications", json=payload)

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


async def _main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Smoke-test the Overseerr API client")
    parser.add_argument("--user-id", type=int, help="User ID to fetch/update")
    parser.add_argument("--discord-id", type=str, help="Discord ID to set for the user")
    args = parser.parse_args()

    client = OverseerrClient()
    try:
        logger.info("Status: %s", await client.get_status())
        users = await client.get_users()
        logger.info("Users: %s", json.dumps(users, indent=2)[:1000])

        if args.user_id:
            logger.info("User %s settings: %s", args.user_id, json.dumps(await client.get_user_settings(args.user_id), indent=2)[:1000])
            if args.discord_id:
                logger.info("Updating user %s discord_id to %s", args.user_id, args.discord_id)
                result = await client.update_user_discord_id(args.user_id, args.discord_id)
                logger.info("Updated: %s", json.dumps(result, indent=2))
    except Exception:
        logger.exception("Overseerr API check failed")
        raise
    finally:
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    asyncio.run(_main())
