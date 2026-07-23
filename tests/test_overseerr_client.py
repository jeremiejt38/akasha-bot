import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.overseerr_client import OverseerrClient


class FakeResponse:
    def __init__(self, status, json_data):
        self.status = status
        self._json = json_data

    async def json(self):
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError("HTTP error")


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.request_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def request(self, method, url, **kwargs):
        resp = self.responses[self.request_count]
        self.request_count += 1
        return FakeResponse(resp["status"], resp["json"])


def test_search_media():
    client = OverseerrClient(base_url="https://seerr.test", api_key="key")
    fake_json = {
        "results": [
            {"id": 123, "mediaType": "movie", "title": "Test Movie", "releaseDate": "2024-01-01"}
        ]
    }
    client._session = FakeSession([{"status": 200, "json": fake_json}])

    import asyncio
    result = asyncio.run(client.search_media("test"))
    assert result["results"][0]["title"] == "Test Movie"


def test_find_user_by_singular_discord_id():
    client = OverseerrClient(base_url="https://seerr.test", api_key="key")
    client._session = FakeSession([
        {"status": 200, "json": {"results": [{"id": 42}], "pageInfo": {"pages": 1}}},
        {"status": 200, "json": {"discordId": "123456"}},
    ])

    import asyncio
    result = asyncio.run(client.find_user_by_discord_id("123456"))
    assert result == {"id": 42}


def test_user_request_quota_filters_requested_by():
    client = OverseerrClient(base_url="https://seerr.test", api_key="key")
    now = datetime.now(timezone.utc).isoformat()
    client._session = FakeSession([{
        "status": 200,
        "json": {
            "results": [
                {"requestedBy": {"id": 42}, "createdAt": now, "type": "movie"},
                {"requestedBy": {"id": 42}, "createdAt": now, "type": "tv", "seasons": [{}, {}]},
                {"requestedBy": {"id": 7}, "createdAt": now, "type": "movie"},
            ],
            "pageInfo": {"pages": 1},
        },
    }])

    import asyncio
    quota = asyncio.run(client.get_user_request_quota(42))

    assert quota == {"seerr_remaining_movies": 6, "seerr_remaining_seasons": 1}


def test_request_media():
    client = OverseerrClient(base_url="https://seerr.test", api_key="key")
    fake_json = {"id": 999, "status": 1}
    client._session = FakeSession([{"status": 201, "json": fake_json}])

    import asyncio
    result = asyncio.run(client.request_media("movie", 123, 1))
    assert result["id"] == 999
