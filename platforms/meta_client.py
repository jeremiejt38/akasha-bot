import os
import logging
import aiohttp

logger = logging.getLogger(__name__)

class MetaClient:
    def __init__(self):
        self.base_url = os.getenv("META_GRAPH_BASE_URL", "https://graph.facebook.com/v20.0")
        self.page_access_token = os.getenv("META_PAGE_ACCESS_TOKEN", "")

    async def post(self, path: str, payload: dict):
        if not self.page_access_token:
            raise RuntimeError("META_PAGE_ACCESS_TOKEN is not configured")
        params = {"access_token": self.page_access_token}
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}{path}", params=params, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Meta API POST failed: {resp.status} {body}")
                return body

    async def get(self, path: str, params: dict | None = None):
        if not self.page_access_token:
            raise RuntimeError("META_PAGE_ACCESS_TOKEN is not configured")
        final_params = dict(params or {})
        final_params["access_token"] = self.page_access_token
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}{path}", params=final_params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Meta API GET failed: {resp.status} {body}")
                return body
