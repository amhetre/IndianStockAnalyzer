"""
SYNTHETIC DEMO DATA – used only by `python main.py --demo` and by tests.

Generates a fictional company ("Demo Industries Ltd") with deterministic random
numbers so that the full report layout can be checked without internet access.
Reports built from this data carry a prominent "SYNTHETIC DEMO DATA" banner.
It is never mixed into real analyses.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from data_providers.models import CompanyData, CompanyIdentity, finalize_statement

DEMO_PEERS = {"DEMOPEER1": ("Demo Peer One Ltd (synthetic)", 1.1, 7),
              "DEMOPEER2": ("Demo Peer Two Ltd (synthetic)", 0.8, 11),
              "DEMOPEER3": ("Demo Peer Three Ltd (synthetic)", 1.4, 23)}


def _annual(seed: int, scale: float, years: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ends = pd.date_range(end=pd.Timestamp("2026-03-31"), periods=years, freq="12ME")
    ends = [pd.Timestamp(year=d.year, month=3, day=31) for d in ends]
    rev = 5000 * scale * np.cumprod(1 + rng.normal(0.12, 0.05, years))
    margin = np.clip(rng.normal(0.18, 0.02, years), 0.08, 0.3)
    op = rev * margin
    dep = rev * 0.04
    other = rev * 0.01
    debt = 2500 * scale * np.cumprod(1 + rng.normal(0.02, 0.08, years))
    interest = debt * 0.085
    pbt = op + other - dep - interest
    tax_pct = np.full(years, 25.0)
    ni = pbt * (1 - tax_pct / 100)
    shares_cr = 50 * scale
    eps = ni / shares_cr
    equity = 6000 * scale + np.cumsum(ni * 0.7)
    cash = rev * rng.uniform(0.04, 0.09, years)
    total_assets = equity + debt + rev * 0.25
    cl = rev * 0.2
    cfo = ni * rng.uniform(0.85, 1.25, years) + dep
    capex = rev * rng.uniform(0.05, 0.09, years)
    df = pd.DataFrame({
        "revenue": rev, "operating_profit": op, "other_income": other, "depreciation": dep, "interest": interest,
        "pbt": pbt, "tax_pct": tax_pct, "tax": pbt * tax_pct / 100, "net_income": ni, "eps_basic": eps,
        "total_equity": equity, "total_debt": debt, "short_term_debt": debt * 0.3, "long_term_debt": debt * 0.7,
        "cash": cash, "total_assets": total_assets, "current_liabilities": cl, "cfo": cfo, "capex": capex,
    }, index=ends).T
    return finalize_statement(df, {}, "annual")


def _quarterly(annual: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    ends = pd.date_range(end=pd.Timestamp("2026-09-30"), periods=13, freq="QE")
    last_rev = annual.loc["revenue"].iloc[-1] / 4
    rev = last_rev * np.cumprod(1 + rng.normal(0.025, 0.02, 13)) * 0.88
    op = rev * rng.normal(0.18, 0.01, 13)
    dep, other = rev * 0.04, rev * 0.01
    interest = np.full(13, annual.loc["interest"].iloc[-1] / 4) * rng.uniform(0.95, 1.05, 13)
    pbt = op + other - dep - interest
    ni = pbt * 0.75
    shares = annual.loc["net_income"].iloc[-1] / annual.loc["eps_basic"].iloc[-1]
    df = pd.DataFrame({"revenue": rev, "operating_profit": op, "other_income": other, "depreciation": dep,
                       "interest": interest, "pbt": pbt, "net_income": ni, "eps_basic": ni / shares}, index=ends).T
    return finalize_statement(df, {}, "quarterly")


def _prices(seed: int, end_price: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 2)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=2500)
    rets = rng.normal(0.0006, 0.017, len(idx))
    path = np.exp(np.cumsum(rets))
    close = path / path[-1] * end_price
    return pd.DataFrame({"Close": close, "High": close * 1.01, "Low": close * 0.99,
                         "Volume": rng.integers(200_000, 2_000_000, len(idx))}, index=idx)


def make_demo_company(symbol: str = "DEMOIND", name: str = "Demo Industries Ltd (SYNTHETIC)",
                      scale: float = 1.0, seed: int = 42, pledge_level: float = 3.0,
                      with_peers: bool = True) -> CompanyData:
    ident = CompanyIdentity(name=name, nse_symbol=symbol, bse_code="999999", yahoo_ticker=f"{symbol}.NS",
                            isin="INE000DEMO01", sector="Industrials (synthetic)", industry="Capital goods (synthetic)",
                            sector_class="manufacturing", exchange="NSE", currency="INR", resolved_by="Demo mode")
    d = CompanyData(identity=ident, is_demo=True)
    d.annual = _annual(seed, scale)
    d.quarterly = _quarterly(d.annual, seed)
    eps_ttm = float(d.quarterly.loc["eps_basic"].iloc[-4:].sum())
    price = eps_ttm * (22 + seed % 10)
    hist = _prices(seed, price)
    d.price_history = hist
    bench = _prices(7, 24000)["Close"] * np.exp(np.random.default_rng(seed).normal(0, 0.002, len(hist)))
    d.benchmark_history = bench
    shares_cr = float(d.annual.loc["net_income"].iloc[-1] / d.annual.loc["eps_basic"].iloc[-1])
    d.quote = {"source": "SYNTHETIC DEMO DATA", "price": float(hist["Close"].iloc[-1]),
               "prev_close": float(hist["Close"].iloc[-2]), "last_price_date": hist.index[-1],
               "high_52w": float(hist["High"].iloc[-250:].max()), "low_52w": float(hist["Low"].iloc[-250:].min()),
               "volume": float(hist["Volume"].iloc[-1]), "market_cap_cr": float(hist["Close"].iloc[-1]) * shares_cr,
               "currency": "INR"}
    d.statement_source = "SYNTHETIC DEMO DATA"
    d.statement_basis = "Consolidated (synthetic)"
    q_idx = pd.date_range(end=pd.Timestamp("2026-09-30"), periods=13, freq="QE")
    rng = np.random.default_rng(seed + 3)
    prom = 55 - np.cumsum(np.abs(rng.normal(0.08, 0.1, 13)))
    fii = 18 + np.cumsum(rng.normal(0.1, 0.3, 13))
    dii = 12 + np.cumsum(rng.normal(0.15, 0.2, 13))
    gov = np.full(13, 0.2)
    public = 100 - prom - fii - dii - gov
    d.shareholding = pd.DataFrame({"promoters": prom, "fii": fii, "dii": dii, "government": gov, "public": public,
                                   "num_shareholders": np.linspace(150000, 260000, 13).round()}, index=q_idx)
    d.shareholding.loc[q_idx[5]] = np.nan  # deliberately missing quarter -> shown as missing
    d.shareholding = d.shareholding.dropna(how="all")
    d.shareholding_source = "SYNTHETIC DEMO DATA"
    d.pledge = pd.DataFrame({"pledged_pct_of_promoter": np.linspace(pledge_level + 2, pledge_level, 13),
                             "pledged_pct_of_total": np.linspace(pledge_level + 2, pledge_level, 13) * 0.55},
                            index=q_idx)
    d.pledge_source = "SYNTHETIC DEMO DATA"
    if with_peers:
        d.peers = [{"name": v[0], "symbol": k, "source": "SYNTHETIC DEMO peer list"} for k, v in DEMO_PEERS.items()]
    for ds in ("CMP & price history", "Financial statements", "Shareholding pattern", "Promoter pledge"):
        d.add_source(ds, "SYNTHETIC DEMO DATA", "", "", "OK", "Fictional numbers for layout demonstration only")
    return d


def demo_peer_loader(symbol: str) -> Optional[CompanyData]:
    if symbol not in DEMO_PEERS:
        return None
    name, scale, seed = DEMO_PEERS[symbol]
    return make_demo_company(symbol, name, scale, seed, with_peers=False)
