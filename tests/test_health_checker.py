import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.health_checker import HealthChecker


def test_format_results_ok_and_ko():
    checker = HealthChecker(urls=[
        {"name": "Test OK", "url": "https://example.com"},
        {"name": "Test KO", "url": "https://bad.example.com"},
    ])
    results = [
        {"name": "Test OK", "url": "https://example.com", "ok": True, "status": 200, "error": None},
        {"name": "Test KO", "url": "https://bad.example.com", "ok": False, "status": None, "error": "Connection refused"},
    ]
    text = checker.format_results(results)
    assert "🟢 Test OK" in text
    assert "🔴 Test KO" in text
    assert "Connection refused" in text


def test_default_urls():
    checker = HealthChecker()
    names = [u["name"] for u in checker.urls]
    assert "Plex" in names
    assert "Seerr" in names
    assert "Inscriptions" in names
    assert "JellyFin" in names
    assert "Site Web" in names
