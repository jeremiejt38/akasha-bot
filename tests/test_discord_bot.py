import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from discord_bot import _truncate_text_for_discord


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
