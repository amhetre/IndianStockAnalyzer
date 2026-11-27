"""Offline tests for portfolio maths, watchlist and alert firing (prices mocked)."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def pf(monkeypatch):
    from server import portfolio
    monkeypatch.setattr(portfolio, "DB_PATH", __import__("pathlib").Path(tempfile.mkdtemp()) / "t.db")
    book = {"TCS.NS": {"price": 110.0, "prev_close": 100.0}, "INFY.NS": {"price": None, "prev_close": None}}
    monkeypatch.setattr(portfolio, "prices", lambda tks: {t: book.get(t, {"price": None, "prev_close": None}) for t in tks})
    monkeypatch.setattr(portfolio, "send_telegram", lambda text: False)
    return portfolio, book


def test_symbol_normalisation(pf):
    p, _ = pf
    assert p.normalize_symbol("tcs") == "TCS.NS"
    assert p.normalize_symbol("500570") == "500570.BO"
    assert p.normalize_symbol("TCS.BO") == "TCS.BO"


def test_lots_merge_and_pnl(pf):
    p, _ = pf
    p.add_holding("TCS", "TCS", 10, 90, None)
    p.add_holding("TCS.NS", "TCS", 10, 110, None)
    r = p.get_portfolio()
    pos = r["positions"][0]
    assert pos["qty"] == 20 and pos["avg_price"] == 100
    assert pos["value"] == 2200 and pos["pnl"] == 200 and pos["pnl_pct"] == 10
    assert pos["day_pnl"] == 200 and pos["weight"] == 100
    assert r["totals"]["complete"] is True


def test_unpriced_holding_not_counted_as_zero(pf):
    p, _ = pf
    p.add_holding("INFY", None, 5, 1500, None)
    r = p.get_portfolio()
    assert r["positions"][0]["value"] is None
    assert r["totals"]["complete"] is False
    assert r["totals"]["invested"] == 7500 and r["totals"]["priced_invested"] == 0 and r["totals"]["pnl"] == 0


def test_invalid_holding_rejected(pf):
    p, _ = pf
    with pytest.raises(ValueError):
        p.add_holding("TCS", None, 0, 100, None)


def test_alert_fires_once(pf):
    p, _ = pf
    p.add_watch("TCS", "TCS", alert_above=105, alert_below=50)
    fired = p.check_alerts()
    assert [(f["kind"], f["level"]) for f in fired] == [("above", 105)]
    assert p.check_alerts() == []
    w = p.get_watchlist()["items"][0]
    assert w["alert_above"] is None and w["alert_below"] == 50
    assert len(p.recent_alerts()) == 1
