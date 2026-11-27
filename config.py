"""
Central configuration for IndianStockAnalyzer.

Every valuation assumption used in WACC / ROIC calculations lives here and is
printed in the "Data Sources and Assumptions" sheet and dashboard section.
Edit these values (or override them on the command line) – nothing is silently
hard-coded inside the analysis modules.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
CACHE_DIR = BASE_DIR / "cache"
TEMPLATE_DIR = BASE_DIR / "templates"

for _d in (OUTPUT_DIR, LOG_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


@dataclass
class ValuationAssumptions:
    """Assumptions for cost of capital. All rates are decimals (0.07 = 7%)."""

    # India 10-year Government bond yield used as the risk-free rate.
    # Update this to the current 10Y G-Sec yield before running.
    risk_free_rate: float = float(os.getenv("ISA_RISK_FREE", "0.065"))
    # Equity risk premium for India (mature-market ERP + country risk premium).
    equity_risk_premium: float = float(os.getenv("ISA_ERP", "0.07"))
    # Used only if beta cannot be computed from price data or obtained from Yahoo.
    default_beta: float = 1.0
    # Benchmark index used to compute beta from price history.
    beta_benchmark: str = "^NSEI"
    beta_lookback_years: int = 3
    # Indian statutory corporate tax rate under section 115BAA incl. surcharge & cess.
    statutory_tax_rate: float = 0.2517
    # Effective tax rates outside this band are considered unreliable -> statutory used.
    min_reliable_tax_rate: float = 0.05
    max_reliable_tax_rate: float = 0.40
    # Pre-tax cost of debt used if it cannot be derived from interest / average debt.
    default_cost_of_debt: float = 0.09
    # Derived cost of debt outside this band is considered unreliable.
    min_reliable_cost_of_debt: float = 0.03
    max_reliable_cost_of_debt: float = 0.20
    # Cash kept for operations (as % of revenue). Cash above this is "excess cash"
    # and is deducted from invested capital for ROIC.
    operating_cash_pct_of_revenue: float = 0.02

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class NetworkSettings:
    timeout_seconds: int = 20
    max_retries: int = 3
    backoff_seconds: float = 2.0
    # Minimum delay between two requests to the same host (politeness / rate limit).
    min_delay_per_host: float = 1.5
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 IndianStockAnalyzer/1.0"
    )
    # Cache time-to-live in hours
    cache_ttl_prices_hours: float = 4.0
    cache_ttl_fundamentals_hours: float = 24.0


@dataclass
class AnalysisSettings:
    default_periods: list = field(default_factory=lambda: ["3M", "6M", "9M", "1Y", "3Y", "5Y"])
    max_peers: int = 5
    # CMP older than this many calendar days is flagged as stale.
    stale_price_days: int = 4
    # Latest financial year older than this many days is flagged as stale.
    stale_financials_days: int = 500
    prefer_consolidated: bool = True
    html_plotly_js: str = "inline"  # "inline" (works offline) or "cdn" (smaller file)


ASSUMPTIONS = ValuationAssumptions()
NETWORK = NetworkSettings()
SETTINGS = AnalysisSettings()


# ---------------------------------------------------------------------------
# Sector classification keywords (matched against Yahoo/Screener sector text).
# ---------------------------------------------------------------------------
SECTOR_KEYWORDS = {
    "bank": ["bank"],
    "nbfc": ["nbfc", "non banking", "finance company", "credit services", "housing finance",
             "consumer finance", "financial services", "capital markets", "finance"],
    "insurance": ["insurance"],
    "it_services": ["information technology", "it services", "software", "it consulting",
                    "computers - software", "it - software", "technology services"],
    "infrastructure": ["infrastructure", "construction", "engineering", "power", "utilities",
                       "utility", "ports", "roads", "telecom infrastructure"],
    "real_estate": ["real estate", "realty", "property", "housing"],
    "manufacturing": ["auto", "automobile", "manufactur", "steel", "metal", "cement", "chemical",
                      "industrial", "machinery", "textile", "pharma", "drug", "consumer",
                      "fmcg", "food", "packaging", "paper", "tyres", "oil", "gas", "refin",
                      "energy", "mining", "electrical", "capital goods"],
}

# Fallback peer lists (NSE symbols) when Screener's peer list is not reachable.
# Clearly labelled in reports as "configured fallback peer list".
FALLBACK_PEERS = {
    "bank": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA"],
    "nbfc": ["BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "SHRIRAMFIN", "MUTHOOTFIN", "LICHSGFIN"],
    "insurance": ["SBILIFE", "HDFCLIFE", "ICICIPRULI", "ICICIGI", "LICI"],
    "it_services": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM"],
    "infrastructure": ["LT", "NTPC", "POWERGRID", "ADANIPORTS", "IRB", "GMRAIRPORT"],
    "real_estate": ["DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "LODHA"],
    "auto": ["TATAMOTORS", "MARUTI", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "TVSMOTOR"],
    "oil_gas": ["RELIANCE", "ONGC", "IOC", "BPCL", "HINDPETRO", "GAIL"],
    "fmcg": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO"],
    "pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "LUPIN", "ZYDUSLIFE"],
    "metals": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "SAIL", "JINDALSTEL"],
    "cement": ["ULTRACEMCO", "SHREECEM", "AMBUJACEM", "ACC", "DALBHARAT"],
}

FALLBACK_PEER_KEYWORDS = {
    "auto": ["auto", "automobile", "vehicle"],
    "oil_gas": ["oil", "gas", "refin", "petro"],
    "fmcg": ["fmcg", "household", "personal products", "packaged foods", "tobacco", "consumer staples"],
    "pharma": ["pharma", "drug", "healthcare"],
    "metals": ["steel", "metal", "aluminium", "mining"],
    "cement": ["cement", "building materials"],
}

SCORE_WEIGHTS = {
    "Profitability and returns": 20,
    "Growth": 15,
    "Valuation": 15,
    "Debt and financial risk": 15,
    "ROIC vs WACC": 15,
    "Cash flow": 10,
    "Promoter and shareholder pattern": 10,
}

SCORE_LABELS = [
    (75, "Strong fundamentals"),
    (60, "Good fundamentals"),
    (45, "Average fundamentals"),
    (30, "Weak fundamentals"),
    (0, "High financial risk"),
]

DISCLAIMER = (
    "This report is generated automatically from publicly available data for educational "
    "purposes only. It is not investment advice and not a recommendation to buy, sell or hold "
    "any security. Data may be delayed, incomplete or incorrect. Verify with the company's "
    "official filings on NSE/BSE and consult a SEBI-registered investment adviser before investing."
)
