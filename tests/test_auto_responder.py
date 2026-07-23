import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.auto_responder import AutoResponder


def test_greeting_match():
    responder = AutoResponder(threshold=80)
    assert responder.respond("Salut !") == "Salut ! Je suis le bot assistant d'Akasha. Comment puis-je t'aider ?"


def test_no_match():
    responder = AutoResponder(threshold=80)
    assert responder.respond("xyzqr12345") is None


def test_subscription_expiration_personalized():
    responder = AutoResponder(threshold=80)
    user = {"wizarr_invite_expires": "2026-07-12T09:10:06.527894"}
    assert "12/07/2026" in responder.respond("Mon compte expire quand ?", user)


def test_subscription_expiration_no_user():
    responder = AutoResponder(threshold=80)
    assert "pas trouvé" in responder.respond("Mon compte expire quand ?")


def test_join_akasha():
    responder = AutoResponder(threshold=80)
    assert "akasha.ing" in responder.respond("Comment rejoindre Akasha ?")


def test_custom_data_path():
    data = [
        {"patterns": ["test custom"], "answer": "réponse custom"},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    try:
        responder = AutoResponder(threshold=80, data_path=path)
        assert responder.respond("test custom") == "réponse custom"
        assert responder.respond("salut") is None
    finally:
        os.unlink(path)


def test_reload_picks_up_new_data():
    data = [{"patterns": ["avant"], "answer": "réponse avant"}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    try:
        responder = AutoResponder(threshold=80, data_path=path)
        assert responder.respond("avant") == "réponse avant"

        with open(path, "w", encoding="utf-8") as f:
            json.dump([{"patterns": ["après"], "answer": "réponse après"}], f)

        responder.reload()
        assert responder.respond("avant") is None
        assert responder.respond("après") == "réponse après"
    finally:
        os.unlink(path)
