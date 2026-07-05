import os
import asyncio
import logging
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
        headers = {"X-Api-Key": self.api_key}
        if json is not None:
            headers["Content-Type"] = "application/json"
        session = await self._session_ctx()
        async with session.request(method, url, headers=headers, json=json, params=params) as resp:
            resp.raise_for_status()
            if resp.status == 204:
                return None
            return await resp.json()

    async def get_status(self):
        return await self._request("GET", "/status")

    async def get_users(self, page: int = 1, limit: int = 10):
        return await self._request("GET", "/user", params={"page": page, "limit": limit})

    async def get_user(self, user_id: int):
        return await self._request("GET", f"/user/{user_id}")

    async def get_user_settings(self, user_id: int):
        return await self._request("GET", f"/user/{user_id}/settings/notifications")

    async def get_user_discord_ids(self, user_id: int):
        settings = await self.get_user_settings(user_id)
        return settings.get("discordIds") or []

    async def find_user_by_email(self, email: str):
        email = email.lower().strip()
        page = 1
        while True:
            data = await self.get_users(page=page, limit=100)
            for user in data.get("results", []):
                if (user.get("email") or "").lower().strip() == email:
                    return user
            page_info = data.get("pageInfo", {})
            if page >= page_info.get("pages", 1):
                break
            page += 1
        return None

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
