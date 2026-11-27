"""Tests for parsing, company resolution (offline, mocked) and report generation."""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.runner import run_analysis  # noqa: E402
from data_providers.demo_provider import demo_peer_loader, make_demo_company  # noqa: E402
from data_providers.provider_manager import AmbiguousCompany, ProviderManager, classify_sector  # noqa: E402
from data_providers.screener_provider import ScreenerProvider  # noqa: E402

SCREENER_HTML = """
<html><body><h1>Test Motors Ltd</h1>
<div id="company-info" data-company-id="123" data-warehouse-id="456"></div>
<a href="https://www.bseindia.com/x">BSE: 500570</a> <a href="https://www.nseindia.com/x">NSE: TESTMOTORS</a>
<ul id="top-ratios"><li><span class="name">Market Cap</span><span class="value">₹ <span class="number">1,000</span> Cr.</span></li>
<li><span class="name">Current Price</span><span class="value">₹ <span class="number">250</span></span></li></ul>
<section id="quarters"><table class="data-table"><thead><tr><th></th><th>Jun 2024</th><th>Sep 2024</th></tr></thead>
<tbody><tr><td>Sales&nbsp;+</td><td>100</td><td>110</td></tr><tr><td>Net Profit&nbsp;+</td><td>10</td><td>12</td></tr></tbody></table></section>
<section id="profit-loss"><table class="data-table"><thead><tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>TTM</th></tr></thead><tbody>
<tr><td>Sales&nbsp;+</td><td>1,000</td><td>1,200</td><td>1,300</td></tr>
<tr><td>Interest</td><td>20</td><td>25</td><td>26</td></tr>
<tr><td>Depreciation</td><td>30</td><td>35</td><td>36</td></tr>
<tr><td>Profit before tax</td><td>100</td><td>120</td><td>130</td></tr>
<tr><td>Tax %</td><td>25%</td><td>25%</td><td></td></tr>
<tr><td>Net Profit&nbsp;+</td><td>75</td><td>90</td><td>97</td></tr>
<tr><td>EPS in Rs</td><td>7.5</td><td>9.0</td><td>9.7</td></tr></tbody></table></section>
<section id="balance-sheet"><table class="data-table"><thead><tr><th></th><th>Mar 2023</th><th>Mar 2024</th></tr></thead><tbody>
<tr><td>Equity Capital</td><td>10</td><td>10</td></tr><tr><td>Reserves</td><td>490</td><td>560</td></tr>
<tr><td>Borrowings&nbsp;+</td><td>200</td><td>-</td></tr><tr><td>Total Assets</td><td>900</td><td>1,000</td></tr></tbody></table></section>
<section id="cash-flow"><table class="data-table"><thead><tr><th></th><th>Mar 2023</th><th>Mar 2024</th></tr></thead><tbody>
<tr><td>Cash from Operating Activity&nbsp;+</td><td>80</td><td>95</td></tr></tbody></table></section>
<section id="shareholding"><div id="quarterly-shp"><table class="data-table"><thead><tr><th></th><th>Jun 2024</th><th>Sep 2024</th></tr></thead><tbody>
<tr><td>Promoters&nbsp;+</td><td>50.10%</td><td>49.90%</td></tr><tr><td>FIIs&nbsp;+</td><td>20.00%</td><td>21.00%</td></tr>
<tr><td>DIIs&nbsp;+</td><td>15.00%</td><td>15.50%</td></tr><tr><td>Public&nbsp;+</td><td>14.90%</td><td>13.60%</td></tr></tbody></table></div></section>
</body></html>
"""


def test_screener_parser():
    p = ScreenerProvider().parse_company_html(SCREENER_HTML, "https://www.screener.in/company/TESTMOTORS/consolidated/")
    a = p["annual"]
    c24 = pd.Timestamp("2024-03-31")
    assert p["basis"] == "Consolidated"
    assert p["bse_code"] == "500570" and p["nse_symbol"] == "TESTMOTORS"
    assert p["company_id"] == "123"
    assert a.at["revenue", c24] == 1200
    assert a.at["ebit", c24] == 145                 # PBT + interest
    assert a.at["ebitda", c24] == 180               # + depreciation
    assert a.at["tax", c24] == pytest.approx(30)
    assert a.at["total_equity", c24] == 570
    assert pd.isna(a.at["total_debt", c24])         # '-' stays missing, never 0
    assert p["ttm"]["eps_basic"] == 9.7
    assert p["shareholding"]["promoters"].iloc[-1] == 49.90
    assert ScreenerProvider.top_ratio(p, "Market Cap") == 1000


class FakeYahoo:
    name = "fake"
    available = True

    def get_info(self, t):
        return {}

    def search(self, q):
        return [{"name": "Tata Motors Ltd", "yahoo_ticker": "TATAMOTORS.NS", "nse_symbol": "TATAMOTORS"},
                {"name": "Tata Motors Passenger Vehicles Ltd", "yahoo_ticker": "TMPV.NS", "nse_symbol": "TMPV"},
                {"name": "Tata Steel Ltd", "yahoo_ticker": "TATASTEEL.NS", "nse_symbol": "TATASTEEL"}]


class FakeScreener:
    name = "fake"

    def search(self, q):
        return []

    def fetch_company(self, *a, **k):
        from utils.http_client import FetchError
        raise FetchError("offline")


def test_resolution_exact_name_and_ambiguity():
    pm = ProviderManager(yahoo=FakeYahoo(), screener=FakeScreener(), nse=None, use_nse=False)
    ident = pm.resolve("Tata Motors Ltd")
    assert ident.nse_symbol == "TATAMOTORS"
    with pytest.raises(AmbiguousCompany) as e:
        pm.resolve("Tata")
    assert len(e.value.candidates) == 3          # shows list, never silently picks


def test_sector_classification():
    assert classify_sector("Banks - Regional", "Financial Services") == "bank"
    assert classify_sector("Insurance - Life") == "insurance"
    assert classify_sector("Information Technology Services", "Technology") == "it_services"
    assert classify_sector("Housing Finance") == "nbfc"
    assert classify_sector("Real Estate - Development") == "real_estate"
    assert classify_sector("Auto Manufacturers", "Consumer Cyclical") == "manufacturing"


def test_full_demo_pipeline_generates_reports():
    from openpyxl import load_workbook
    from reporting.excel_report import build_excel
    from reporting.html_report import build_html
    d = make_demo_company()
    res = run_analysis(d, ["3M", "6M", "9M", "1Y", "3Y", "5Y"], demo_peer_loader)
    assert res["peers"]["n_peers"] == 3
    assert res["score"]["overall"] is not None
    with tempfile.TemporaryDirectory() as tmp:
        x = build_excel(res, Path(tmp) / "t.xlsx")
        h = build_html(res, Path(tmp) / "t.html")
        wb = load_workbook(x)
        assert len(wb.sheetnames) == 18          # 14 analysis sheets + 4 learning-centre sheets
        assert any(n.startswith("Learn") for n in wb.sheetnames)
        html = h.read_text(encoding="utf-8")
        assert "SYNTHETIC DEMO DATA" in html and "Plotly" in html
        assert "Stock market basics" in html       # learning centre present
        assert "Benchmark" in html
        assert html.count('class="hint"') > 10     # '!' formula tooltips


def test_provider_manager_load_merges_sources_without_mixing():
    """load(): Yahoo for prices, Screener for statements/shareholding, Yahoo only fills missing items."""
    import numpy as np
    from data_providers.models import CompanyIdentity

    parsed = ScreenerProvider().parse_company_html(SCREENER_HTML, "https://www.screener.in/company/TESTMOTORS/consolidated/")

    class Y(FakeYahoo):
        def get_info(self, t):
            return {"longName": "Test Motors Limited", "currentPrice": 250.0, "previousClose": 245.0,
                    "marketCap": 1.0e10, "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"}

        def get_history(self, t, period="10y"):
            idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=600)
            return pd.DataFrame({"Close": np.linspace(150, 250, 600), "Volume": 1000}, index=idx)

        def build_quote(self, t, info, hist):
            from data_providers.yahoo_provider import YahooProvider
            return YahooProvider.build_quote(self, t, info, hist)

        def get_statements(self, t):
            ann = pd.DataFrame({pd.Timestamp("2024-03-31"): {"cash": 55.0, "revenue": 9999.0}})
            return {"annual": ann, "quarterly": pd.DataFrame(), "item_sources": {}}

    class S(FakeScreener):
        def fetch_company(self, *a, **k):
            return parsed

        def enrich_with_schedules(self, p):
            pass

        def fetch_peers(self, *a):
            return [{"name": "Peer", "symbol": "PEER", "source": "Screener.in peer list"}]

    pm = ProviderManager(yahoo=Y(), screener=S(), nse=None, use_nse=False)
    d = pm.load(CompanyIdentity(name="TESTMOTORS", nse_symbol="TESTMOTORS", yahoo_ticker="TESTMOTORS.NS"))
    c24 = pd.Timestamp("2024-03-31")
    assert d.statement_source == "Screener.in" and d.statement_basis == "Consolidated"
    assert d.annual.at["revenue", c24] == 1200           # Screener value kept, Yahoo's 9999 ignored
    assert d.annual.at["cash", c24] == 55.0              # missing item supplemented for same period
    assert "Yahoo" in d.item_sources["annual:cash"]
    assert d.quote["price"] == 250.0 and d.quote["market_cap_cr"] == pytest.approx(1000.0)
    assert d.identity.bse_code == "500570"
    assert d.identity.sector_class == "manufacturing"
    assert not d.shareholding.empty and d.peers[0]["symbol"] == "PEER"
    res = run_analysis(d, ["3M", "1Y", "3Y"], None)
    assert res["ratios"]["pe"].available
