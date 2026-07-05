import sys
import os
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from platforms.meta_common import (
    MetaPlatform,
    detect_meta_platform,
    extract_meta_entries,
)
from platforms.instagram import InstagramPlatform
from platforms.facebook import FacebookPlatform
from platforms.meta_client import MetaClient


def _mock_aiohttp_session(status=200, body='{"id":"123"}'):
    session = MagicMock()
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=resp)
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def test_detect_meta_platform_instagram():
    assert detect_meta_platform({"object": "instagram"}) == "instagram"


def test_detect_meta_platform_messenger():
    assert detect_meta_platform({"object": "page"}) == "messenger"


def test_detect_meta_platform_unknown():
    assert detect_meta_platform({"object": "unknown"}) is None


def test_extract_meta_entries():
    assert extract_meta_entries({"entry": [{"id": "1"}]}) == [{"id": "1"}]
    assert extract_meta_entries("bad") == []


def test_meta_client_post_success():
    session = _mock_aiohttp_session()
    with patch("platforms.meta_client.aiohttp.ClientSession", return_value=session):
        client = MetaClient()
        client.page_access_token = "token"
        client.base_url = "https://graph.facebook.com/v20.0"
        result = asyncio.run(
            client.post("/me/messages", {"recipient": {"id": "1"}, "message": {"text": "hi"}})
        )
        assert session.post.call_count == 1
        _, kwargs = session.post.call_args
        assert kwargs["params"]["access_token"] == "token"
        assert kwargs["json"]["message"]["text"] == "hi"
        assert json.loads(result)["id"] == "123"


def test_meta_client_post_error():
    session = _mock_aiohttp_session(status=400, body='{"error":"oops"}')
    with patch("platforms.meta_client.aiohttp.ClientSession", return_value=session):
        client = MetaClient()
        client.page_access_token = "token"
        client.base_url = "https://graph.facebook.com/v20.0"
        try:
            asyncio.run(client.post("/me/messages", {}))
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "400" in str(exc)


def test_meta_client_missing_token():
    client = MetaClient()
    client.page_access_token = ""
    try:
        asyncio.run(client.post("/me/messages", {}))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "META_PAGE_ACCESS_TOKEN" in str(exc)


def test_instagram_handle_webhook_text():
    discord = MagicMock()
    discord.post_inbound_message = AsyncMock()
    ig = InstagramPlatform(discord=discord, db=None)
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "123456",
                "messaging": [
                    {
                        "sender": {"id": "777"},
                        "recipient": {"id": "123456"},
                        "message": {
                            "text": "Hello",
                            "attachments": [
                                {"type": "image", "payload": {"url": "https://example.com/img.jpg"}}
                            ],
                        },
                    }
                ],
            }
        ],
    }
    asyncio.run(ig.handle_webhook(payload))
    assert discord.post_inbound_message.await_count == 1
    args, _ = discord.post_inbound_message.call_args
    assert args[0] == "IG"
    assert args[1] == "777"
    assert "IG 777" in args[2]
    assert "Hello" in args[3]
    assert "[Attachment: https://example.com/img.jpg]" in args[3]


def test_facebook_handle_webhook_text():
    discord = MagicMock()
    discord.post_inbound_message = AsyncMock()
    fb = FacebookPlatform(discord=discord, db=None)
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page1",
                "messaging": [
                    {
                        "sender": {"id": "888"},
                        "recipient": {"id": "page1"},
                        "message": {"text": "Salut"},
                    }
                ],
            }
        ],
    }
    asyncio.run(fb.handle_webhook(payload))
    assert discord.post_inbound_message.await_count == 1
    args, _ = discord.post_inbound_message.call_args
    assert args[0] == "FB"
    assert args[1] == "888"
    assert args[3] == "Salut"


def test_meta_handle_webhook_ignores_echo():
    discord = MagicMock()
    discord.post_inbound_message = AsyncMock()
    fb = FacebookPlatform(discord=discord, db=None)
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page1",
                "messaging": [
                    {
                        "sender": {"id": "888"},
                        "recipient": {"id": "page1"},
                        "message": {"is_echo": True, "text": "echo"},
                    }
                ],
            }
        ],
    }
    asyncio.run(fb.handle_webhook(payload))
    discord.post_inbound_message.assert_not_awaited()


def test_meta_send_text():
    session = _mock_aiohttp_session()
    with patch("platforms.meta_client.aiohttp.ClientSession", return_value=session):
        discord = MagicMock()
        fb = FacebookPlatform(discord=discord, db=None)
        fb.page_id = "page1"
        fb.client.page_access_token = "token"
        asyncio.run(fb.send("888", "reply"))
        assert session.post.call_count == 1
        _, kwargs = session.post.call_args
        assert kwargs["json"]["recipient"]["id"] == "888"
        assert kwargs["json"]["message"]["text"] == "reply"


def test_meta_send_requires_page_id():
    discord = MagicMock()
    fb = FacebookPlatform(discord=discord, db=None)
    fb.page_id = ""
    try:
        asyncio.run(fb.send("888", "reply"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "page/account ID not configured" in str(exc)


def test_meta_start_logs_missing_config():
    discord = MagicMock()
    fb = FacebookPlatform(discord=discord, db=None)
    fb.page_id = ""
    fb.client.page_access_token = ""
    asyncio.run(fb.start())
