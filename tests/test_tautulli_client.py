import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.tautulli_client import TautulliClient


def test_normalize_tautulli_statistics():
    assert TautulliClient._normalize_statistics({
        "movie_count": "4",
        "episode_count": "12",
        "total_time": "183600",
    }) == {"movies": 4, "episodes": 12, "total_seconds": 183600}


def test_normalize_tautulli_statistics_defaults_to_zero():
    assert TautulliClient._normalize_statistics({}) == {"movies": 0, "episodes": 0, "total_seconds": 0}


def test_library_statistics_normalizes_accents_and_hyphens():
    client = TautulliClient(base_url="https://tautulli.test", api_key="key")

    async def request(command, **params):
        return {"data": [
            {"section_name": "Animés", "count": "85"},
            {"section_name": "Docu-séries", "count": "52"},
        ]}

    client._request = request
    assert asyncio.run(client.get_library_statistics()) == {"animes": 85, "docu series": 52}
