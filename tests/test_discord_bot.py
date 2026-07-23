import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from discord_bot import DiscordBridge, _truncate_text_for_discord


def test_truncate_text_short():
    result = _truncate_text_for_discord("hello", "[WA]John")
    assert result == "**[WA]John**: hello"


def test_truncate_text_long():
    text = "x" * 3000
    result = _truncate_text_for_discord(text, "[WA]John")
    assert len(result) <= 2000
    assert result.endswith("...")
    assert result.startswith("**[WA]John**: ")


def test_truncate_text_empty():
    result = _truncate_text_for_discord("", "[WA]John")
    assert result == "**[WA]John**"


def test_dynamic_faq_library_mapping_prefers_exact_names():
    class Tautulli:
        configured = True

        async def get_library_statistics(self):
            return {
                "animes": 85,
                "dessins animes": 749,
                "docu series": 52,
                "films": 4811,
                "series tv": 412,
            }

        async def get_active_stream_count(self):
            return 3

    bridge = object.__new__(DiscordBridge)
    bridge._faq_statistics_cache = None
    bridge.tautulli_client = Tautulli()
    bridge.overseerr_client = None
    bridge.tracearr_client = None

    data = asyncio.run(bridge._get_auto_response_template_data({}))

    assert data["nb_animes"] == 85
    assert data["nb_dessins_animes"] == 749
    assert data["nb_docuseries"] == 52
