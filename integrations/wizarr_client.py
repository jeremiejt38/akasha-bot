import os
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)


class WizarrClient:
    """Async client for the Wizarr REST API.

    Requires environment variables:
      - WIZARR_BASE_URL (e.g. http://192.168.1.29:5690)
      - WIZARR_API_KEY

    Interactive API docs are available at /api/docs/ on your Wizarr instance.
    """

    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or os.getenv("WIZARR_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("WIZARR_API_KEY", "")
        self._session: aiohttp.ClientSession | None = None

    async def _session_ctx(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, path: str, json=None, params=None):
        if not self.base_url or not self.api_key:
            raise RuntimeError("WIZARR_BASE_URL and WIZARR_API_KEY must be configured")
        url = f"{self.base_url}/api{path}"
        headers = {"X-API-Key": self.api_key}
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

    async def get_users(self):
        return await self._request("GET", "/users")

    async def find_user_by_email(self, email: str):
        email = email.lower().strip()
        data = await self._request("GET", "/users", params={"email": email})
        for user in data.get("users", []):
            if (user.get("email") or "").lower().strip() == email:
                return user
        return None

    async def extend_user_expiry(self, user_id: int | str, days: int):
        return await self._request("POST", f"/users/{user_id}/extend", json={"days": days})

    async def get_invitations(self):
        return await self._request("GET", "/invitations")

    async def get_invitation_by_code(self, code: str):
        data = await self.get_invitations()
        for inv in data.get("invitations", []):
            if inv.get("code") == code:
                return inv
        return None

    async def find_invitation_by_email(self, email: str):
        email = email.lower().strip()
        data = await self.get_invitations()
        for inv in data.get("invitations", []):
            if (inv.get("used_by") or "").lower().strip() == email:
                return inv
        return None

    async def get_libraries(self):
        return await self._request("GET", "/libraries")

    async def get_servers(self):
        return await self._request("GET", "/servers")

    async def get_api_keys(self):
        return await self._request("GET", "/api-keys")

    async def create_invitation(
        self,
        server_ids: list,
        expires_in_days: int | None = None,
        duration: str | None = None,
        unlimited: bool = False,
        library_ids: list | None = None,
        allow_downloads: bool = False,
        allow_live_tv: bool = False,
        allow_mobile_uploads: bool = False,
    ):
        payload = {
            "server_ids": server_ids,
            "unlimited": unlimited,
        }
        if expires_in_days is not None:
            payload["expires_in_days"] = expires_in_days
        if duration is not None:
            payload["duration"] = duration
        if library_ids is not None:
            payload["library_ids"] = library_ids
        payload["allow_downloads"] = allow_downloads
        payload["allow_live_tv"] = allow_live_tv
        payload["allow_mobile_uploads"] = allow_mobile_uploads
        return await self._request("POST", "/invitations", json=payload)

    async def delete_invitation(self, invitation_id: int):
        return await self._request("DELETE", f"/invitations/{invitation_id}")

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


async def _main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Smoke-test the Wizarr API client")
    parser.add_argument("--create", action="store_true", help="Also try POST /invitations with the first server id")
    parser.add_argument("--server-id", type=int, default=1, help="Server id to use for the test invitation")
    args = parser.parse_args()

    client = WizarrClient()
    try:
        logger.info("Status: %s", await client.get_status())
        logger.info("Users: %s", json.dumps(await client.get_users(), indent=2)[:500])
        logger.info("Invitations: %s", json.dumps(await client.get_invitations(), indent=2)[:500])

        if args.create:
            logger.info("Creating invitation with server id %s...", args.server_id)
            invitation = await client.create_invitation([args.server_id], expires_in_days=1, unlimited=False)
            logger.info("Created invitation: %s", json.dumps(invitation, indent=2))
    except Exception:
        logger.exception("Wizarr API check failed")
        raise
    finally:
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    asyncio.run(_main())
