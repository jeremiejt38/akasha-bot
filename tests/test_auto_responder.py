import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.auto_responder import AutoResponder


def test_greeting_match():
    responder = AutoResponder(threshold=80)
    assert responder.respond("Salut !") == "👋 Salut ! Je suis le bot assistant d'Akasha. Comment puis-je t'aider ?"


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
    response = responder.respond("Comment rejoindre Akasha ?")
    assert response["marker"] == "notify_admin_signup_request"
    assert "inscription" in response["answer"]


def test_corrected_plex_and_seerr_answers():
    responder = AutoResponder(threshold=80)
    testing_user = {"wizarr_invite_expires": "2030-01-01T00:00:00+00:00", "access_type": "trial"}

    assert "Plex Pass" in responder.respond("Puis-je télécharger un film hors ligne ?", testing_user)
    assert "Seerr" in responder.respond("Comment demander un film ?", testing_user)
    assert "sans publicités" in responder.respond("Est-ce qu'il y a des pubs ?")


def test_tariff_template_uses_environment_value(monkeypatch):
    monkeypatch.setenv("IMG_TARIF", "https://example.test/tarifs.png")
    responder = AutoResponder(threshold=80)

    assert "https://example.test/tarifs.png" in responder.respond("Quels sont les prix ?")


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


def test_min_access_hierarchy():
    data = [
        {"patterns": ["base"], "answer": "base", "min_access": "everyone"},
        {"patterns": ["expired"], "answer": "expired", "fallback": "denied", "min_access": "expired"},
        {"patterns": ["testing"], "answer": "testing", "fallback": "denied", "min_access": "testing"},
        {"patterns": ["subscriber"], "answer": "subscriber", "fallback": "denied", "min_access": "subscriber"},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    try:
        responder = AutoResponder(threshold=100, data_path=path)
        expired = {"wizarr_invite_expires": "2020-01-01T00:00:00+00:00"}
        testing = {"wizarr_invite_expires": "2030-01-01T00:00:00+00:00", "access_type": "trial"}
        subscriber = {"wizarr_invite_expires": "2030-01-01T00:00:00+00:00", "access_type": "subscriber"}

        assert responder.respond("base") == "base"
        assert responder.respond("expired") == "denied"
        assert responder.respond("expired", expired) == "expired"
        assert responder.respond("testing", expired) == "denied"
        assert responder.respond("testing", testing) == "testing"
        assert responder.respond("subscriber", testing) == "denied"
        assert responder.respond("subscriber", subscriber) == "subscriber"
    finally:
        os.unlink(path)
