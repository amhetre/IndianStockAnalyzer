"""Offline tests for production settings: health check, feature switch, API 404s."""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _client(monkeypatch, portfolio: str) -> TestClient:
    monkeypatch.setenv("ISA_ENABLE_PORTFOLIO", portfolio)
    monkeypatch.setenv("ISA_DISABLE_ALERTS", "1")
    import server.app as app_module
    return TestClient(importlib.reload(app_module).app)


def test_health_and_headers(monkeypatch):
    c = _client(monkeypatch, "true")
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("flag,expected", [("false", False), ("0", False), ("true", True)])
def test_config_reports_switch(monkeypatch, flag, expected):
    assert _client(monkeypatch, flag).get("/api/config").json()["portfolio"] is expected


def test_portfolio_blocked_when_disabled(monkeypatch):
    c = _client(monkeypatch, "false")
    for method, url in [("get", "/api/portfolio"), ("get", "/api/watchlist"), ("get", "/api/alerts"),
                        ("post", "/api/alerts/check"), ("delete", "/api/watchlist/TCS")]:
        assert getattr(c, method)(url).status_code == 404, url


def test_unknown_api_path_is_404(monkeypatch):
    assert _client(monkeypatch, "true").get("/api/does-not-exist").status_code == 404


def test_adsense_runtime_config(monkeypatch):
    monkeypatch.setenv("ADSENSE_PUB_ID", "pub-123")
    monkeypatch.setenv("ADSENSE_SLOT_HOME", "999")
    monkeypatch.delenv("ADSENSE_CLIENT", raising=False)
    c = _client(monkeypatch, "false")
    assert c.get("/api/config").json()["adsense"] == {"client": "ca-pub-123", "slots": {"home": "999"}}
    assert c.get("/ads.txt").text == "google.com, pub-123, DIRECT, f08c47fec0942fa0\n"
