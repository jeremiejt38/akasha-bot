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
    monkeypatch.delenv("VERIFICATION_ROLE_NAME", raising=False)
    monkeypatch.delenv("VERIFICATION_CHANNEL_NAME", raising=False)
    monkeypatch.delenv("TRIAL_ROLE_NAME", raising=False)
    monkeypatch.delenv("EXPIRED_ROLE_NAME", raising=False)
    monkeypatch.delenv("EXPIRATION_CHANNEL_NAME", raising=False)
    monkeypatch.delenv("ONBOARDING_ANSWER_ROLE_NAMES", raising=False)

    config = OnboardingConfig()
    assert config.enabled is True
    assert config.member_role_name == "Abonné"
    assert config.create_role is True
    assert config.seerr_signup_url == "https://s.akasha.ing"
    assert config.plex_url == "https://p.akasha.ing"
    assert config.jellyfin_url == "https://j.akasha.ing"
    assert config.support_dm_enabled is True
    assert config.verification_role_name == "À vérifier"
    assert config.verification_channel_name == "verification"
    assert config.trial_role_name == "Essai"
    assert config.expired_role_name == "Expiré"
    assert config.expiration_channel_name == "abonnement-expire"
    assert config.answer_role_names == ("Q1", "Q2", "Q3")


def test_onboarding_config_from_env(monkeypatch):
    monkeypatch.setenv("MEMBER_ROLE_NAME", "Membre")
    monkeypatch.setenv("CREATE_MEMBER_ROLE", "false")
    monkeypatch.setenv("ONBOARDING_DM_ENABLED", "0")
    monkeypatch.setenv("SEERR_SIGNUP_URL", "https://seerr.example.com")
    monkeypatch.setenv("PLEX_URL", "https://plex.example.com")
    monkeypatch.setenv("JELLYFIN_URL", "https://jelly.example.com")
    monkeypatch.setenv("SUPPORT_DM_ENABLED", "no")
    monkeypatch.setenv("VERIFICATION_ROLE_NAME", "Validation requise")
    monkeypatch.setenv("VERIFICATION_CHANNEL_NAME", "lier-mon-compte")
    monkeypatch.setenv("TRIAL_ROLE_NAME", "Découverte")
    monkeypatch.setenv("EXPIRED_ROLE_NAME", "À renouveler")
    monkeypatch.setenv("EXPIRATION_CHANNEL_NAME", "renouvellement")
    monkeypatch.setenv("ONBOARDING_ANSWER_ROLE_NAMES", "Q1_A,Q2_B")

    config = OnboardingConfig()
    assert config.enabled is False
    assert config.member_role_name == "Membre"
    assert config.create_role is False
    assert config.seerr_signup_url == "https://seerr.example.com"
    assert config.plex_url == "https://plex.example.com"
    assert config.jellyfin_url == "https://jelly.example.com"
    assert config.support_dm_enabled is False
    assert config.verification_role_name == "Validation requise"
    assert config.verification_channel_name == "lier-mon-compte"
    assert config.trial_role_name == "Découverte"
    assert config.expired_role_name == "À renouveler"
    assert config.expiration_channel_name == "renouvellement"
    assert config.answer_role_names == ("Q1_A", "Q2_B")
