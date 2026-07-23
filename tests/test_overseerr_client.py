import sys
import os
import json

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


def test_request_media():
    client = OverseerrClient(base_url="https://seerr.test", api_key="key")
    fake_json = {"id": 999, "status": 1}
    client._session = FakeSession([{"status": 201, "json": fake_json}])

    import asyncio
    result = asyncio.run(client.request_media("movie", 123, 1))
    assert result["id"] == 999
