import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.onboarding import OnboardingConfig


def test_onboarding_config_defaults(monkeypatch):
    monkeypatch.delenv("MEMBER_ROLE_NAME", raising=False)
    monkeypatch.delenv("CREATE_MEMBER_ROLE", raising=False)
    monkeypatch.delenv("ONBOARDING_DM_ENABLED", raising=False)
    monkeypatch.delenv("SEERR_SIGNUP_URL", raising=False)
    monkeypatch.delenv("PLEX_URL", raising=False)
    monkeypatch.delenv("JELLYFIN_URL", raising=False)
    monkeypatch.delenv("SUPPORT_DM_ENABLED", raising=False)

    config = OnboardingConfig()
    assert config.enabled is True
    assert config.member_role_name == "Abonné"
    assert config.create_role is True
    assert config.seerr_signup_url == "https://s.akasha.ing"
    assert config.plex_url == "https://p.akasha.ing"
    assert config.jellyfin_url == "https://j.akasha.ing"
    assert config.support_dm_enabled is True


def test_onboarding_config_from_env(monkeypatch):
    monkeypatch.setenv("MEMBER_ROLE_NAME", "Membre")
    monkeypatch.setenv("CREATE_MEMBER_ROLE", "false")
    monkeypatch.setenv("ONBOARDING_DM_ENABLED", "0")
    monkeypatch.setenv("SEERR_SIGNUP_URL", "https://seerr.example.com")
    monkeypatch.setenv("PLEX_URL", "https://plex.example.com")
    monkeypatch.setenv("JELLYFIN_URL", "https://jelly.example.com")
    monkeypatch.setenv("SUPPORT_DM_ENABLED", "no")

    config = OnboardingConfig()
    assert config.enabled is False
    assert config.member_role_name == "Membre"
    assert config.create_role is False
    assert config.seerr_signup_url == "https://seerr.example.com"
    assert config.plex_url == "https://plex.example.com"
    assert config.jellyfin_url == "https://jelly.example.com"
    assert config.support_dm_enabled is False
