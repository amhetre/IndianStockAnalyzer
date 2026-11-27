"""
Indian Stock Market – Fundamental Analysis & Valuation System

Usage:
    python main.py "Tata Motors"
    python main.py "RELIANCE" --exchange NSE
    python main.py "INFY" --periods 3M,6M,9M,1Y,3Y,5Y
    python main.py --demo                      (synthetic data, no internet needed)
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime

# Make ₹ and other symbols print correctly on Windows consoles
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from config import ASSUMPTIONS, OUTPUT_DIR, SETTINGS  # noqa: E402
from utils.financial_utils import fmt_inr  # noqa: E402
from utils.logger import get_logger, setup_logging  # noqa: E402

log = get_logger("main")


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Fundamental & technical analysis of NSE/BSE listed companies.")
    ap.add_argument("query", nargs="?", help="Company name, NSE symbol, BSE code or Yahoo ticker")
    ap.add_argument("--exchange", choices=["NSE", "BSE"], help="Preferred exchange for symbol lookup")
    ap.add_argument("--periods", default=",".join(SETTINGS.default_periods),
                    help="Comma-separated periods from 3M,6M,9M,1Y,3Y,5Y")
    ap.add_argument("--peers", type=int, default=SETTINGS.max_peers, help="Max number of peers (0 = skip)")
    ap.add_argument("--choice", type=int, help="Pick candidate N when the name is ambiguous (non-interactive)")
    ap.add_argument("--risk-free", type=float,
                    help=f"Risk-free rate in percent (default {ASSUMPTIONS.risk_free_rate * 100:.2f})")
    ap.add_argument("--erp", type=float,
                    help=f"Equity risk premium in percent (default {ASSUMPTIONS.equity_risk_premium * 100:.2f})")
    ap.add_argument("--standalone", action="store_true", help="Prefer standalone statements over consolidated")
    ap.add_argument("--no-nse", action="store_true", help="Do not query nseindia.com")
    ap.add_argument("--plotly-cdn", action="store_true", help="Load Plotly from CDN (smaller HTML, needs internet to view)")
    ap.add_argument("--demo", action="store_true", help="Run on SYNTHETIC demo data (no internet)")
    ap.add_argument("-v", "--verbose", action="store_true", help="Verbose console logging")
    a = ap.parse_args(argv)
    if not a.query and not a.demo:
        ap.error("Please provide a company name or symbol, e.g.  python main.py \"Tata Motors\"")
    return a


def step(n: int, text: str) -> None:
    print(f"[{n}/9] {text}", flush=True)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    if args.risk_free is not None:
        ASSUMPTIONS.risk_free_rate = args.risk_free / 100
    if args.erp is not None:
        ASSUMPTIONS.equity_risk_premium = args.erp / 100
    if args.standalone:
        SETTINGS.prefer_consolidated = False
    if args.plotly_cdn:
        SETTINGS.html_plotly_js = "cdn"
    periods = [p.strip().upper() for p in args.periods.split(",") if p.strip()]

    from analysis.runner import run_analysis
    from reporting.excel_report import build_excel
    from reporting.html_report import build_html

    t0 = time.time()
    if args.demo:
        from data_providers.demo_provider import demo_peer_loader, make_demo_company
        step(1, "Resolving company … DEMO mode (synthetic data)")
        step(2, "Retrieving data … synthetic")
        data = make_demo_company()
        data.peers = data.peers[: args.peers]
        peer_loader = demo_peer_loader if args.peers > 0 else None
    else:
        from data_providers.provider_manager import AmbiguousCompany, CompanyNotFound, ProviderManager
        pm = ProviderManager(use_nse=not args.no_nse)
        step(1, f"Resolving company '{args.query}' …")
        try:
            ident = pm.resolve(args.query, args.exchange)
        except AmbiguousCompany as amb:
            if args.choice and 1 <= args.choice <= len(amb.candidates):
                chosen = amb.candidates[args.choice - 1]
            else:
                chosen = ProviderManager.choose_interactively(amb)
            if chosen is None:
                print("No company selected. Exiting.")
                return 2
            ident = pm._identity_from_candidate(chosen, "User selection")
        except CompanyNotFound as exc:
            from utils.http_client import _DOWN_HOSTS
            if _DOWN_HOSTS:
                print("ERROR: Could not reach the data sources (" + ", ".join(sorted(_DOWN_HOSTS)) + "). "
                      "Check your internet connection, proxy or firewall, then try again.")
            else:
                print(f"ERROR: {exc}")
            return 1
        print(f"      → {ident.name} (NSE: {ident.nse_symbol or '-'}, BSE: {ident.bse_code or '-'}, "
              f"Yahoo: {ident.yahoo_ticker or '-'}) [{ident.resolved_by}]")
        step(2, "Retrieving market data, statements, shareholding, peers …")
        data = pm.load(ident, with_peers=args.peers > 0)
        data.peers = data.peers[: args.peers]
        peer_loader = pm.load_peer if args.peers > 0 else None
        if data.annual.empty and not data.quote.get("price"):
            print("ERROR: No market or financial data could be retrieved. Check your internet connection, "
                  "or see logs/analyzer.log for details.")
            return 1

    step(3, "Validating data …")
    for s in data.sources:
        if s.status != "OK":
            print(f"      ! {s.dataset}: {s.status} – {s.note}")
    step(4, "Calculating metrics …")
    res = run_analysis(data, periods, peer_loader, progress=lambda m: print("     ", m, flush=True))
    step(5, "Generating explanations … done")
    step(6, "Generating charts …")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = re.sub(r"[^A-Za-z0-9]+", "_", data.identity.nse_symbol or data.identity.bse_code or data.identity.name).strip("_")
    if data.is_demo:
        base = "DEMO_SYNTHETIC_" + base
    xlsx = OUTPUT_DIR / f"{base}_analysis_{stamp}.xlsx"
    html = OUTPUT_DIR / f"{base}_dashboard_{stamp}.html"
    step(7, "Generating Excel report …")
    build_excel(res, xlsx)
    step(8, "Generating HTML dashboard …")
    build_html(res, html)
    step(9, "Done.")
    sc = res["score"]
    print("\n" + "=" * 70)
    print(f" {data.identity.name}")
    if data.is_demo:
        print(" *** SYNTHETIC DEMO DATA – not a real company ***")
    print(f" CMP: {fmt_inr(res["price"].get("price"))}   Score: "
          f"{sc['overall'] if sc['overall'] is not None else 'N/A'}/100 ({sc['label']}, coverage {sc['coverage_pct']}%)")
    print(f" Data coverage: {res['coverage']['coverage_pct']}%")
    print("=" * 70)
    print(f" Excel report  : {xlsx}")
    print(f" HTML dashboard: {html}")
    print(f" Log file      : logs/analyzer.log   ({time.time() - t0:.1f}s)")
    print(" Not investment advice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
