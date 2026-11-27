"""
FastAPI app.

Run (from the project folder):
    python -m uvicorn server.app:app --port 8000

Production settings (environment variables, see deploy/.env.example):
    ISA_ENABLE_PORTFOLIO  "true" (default) / "false": portfolio, watchlist and alerts.
                          Turn off on a public server until user accounts exist,
                          otherwise every visitor shares one portfolio.
    ISA_CORS_ORIGINS      extra allowed origins, comma separated (only needed when the
                          frontend is served from another domain).

Serves the JSON API under /api and the built React frontend (frontend/dist) at /.
Report tabs are rendered on demand; no Excel/HTML files are generated.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import ipo_detail as ipo_details  # noqa: E402
from server import market, news, portfolio, quote, reports  # noqa: E402
from server import search as fast_search  # noqa: E402
from utils.logger import setup_logging  # noqa: E402

setup_logging(False)


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


PORTFOLIO_ENABLED = _flag("ISA_ENABLE_PORTFOLIO", True)
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"] + [
    o.strip() for o in os.environ.get("ISA_CORS_ORIGINS", "").split(",") if o.strip()]

app = FastAPI(title="Indian Stock Analyzer API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def _cache_headers(request: Request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):  # Vite file names carry a content hash
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/") and "Cache-Control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-store"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


def portfolio_on():
    if not PORTFOLIO_ENABLED:
        raise HTTPException(404, "Portfolio and watchlist are not enabled on this server")


@app.get("/api/health")
def health():
    return {"ok": True}


def _adsense() -> Optional[dict]:
    client = os.environ.get("ADSENSE_CLIENT", "").strip()
    if not client:
        pub = os.environ.get("ADSENSE_PUB_ID", "").strip()
        client = f"ca-{pub}" if pub.startswith("pub-") else pub
    if not client:
        return None
    slots = {k: os.environ.get(f"ADSENSE_SLOT_{k.upper()}", "").strip() for k in ("home", "report", "portfolio")}
    return {"client": client, "slots": {k: v for k, v in slots.items() if v}}


@app.get("/api/config")
def client_config():
    """Runtime settings for the frontend, so one built image works with any configuration."""
    return {"portfolio": PORTFOLIO_ENABLED, "adsense": _adsense()}


# ---------------------------------------------------------------- market
@app.get("/api/market/indices")
def indices():
    return market.get_indices()


@app.get("/api/market/movers")
def movers(n: int = Query(10, ge=1, le=25)):
    return market.get_movers(n)


@app.get("/api/market/ipos")
def ipos():
    return market.get_ipos()


@app.get("/api/ipo/{slug}")
def ipo_detail(slug: str):
    try:
        return ipo_details.get_detail(slug)
    except ipo_details.IpoNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------- quote (instant stock page)
def _ticker(nse, bse, yt) -> str:
    tk = quote.ticker_for(nse, bse, yt)
    if not tk:
        raise HTTPException(400, "Pass nse, bse or yt")
    return tk


@app.get("/api/quote")
def stock_quote(nse: Optional[str] = None, bse: Optional[str] = None, yt: Optional[str] = None):
    return quote.get_quote(_ticker(nse, bse, yt))


@app.get("/api/history")
def stock_history(nse: Optional[str] = None, bse: Optional[str] = None, yt: Optional[str] = None,
                  range: str = Query("1Y", pattern="^(1D|5D|1M|6M|1Y|5Y|MAX)$")):  # noqa: A002
    return quote.get_history(_ticker(nse, bse, yt), range)


@app.get("/api/candles")
def stock_candles(nse: Optional[str] = None, bse: Optional[str] = None, yt: Optional[str] = None,
                  range: str = Query("1D", pattern="^(1D|5D|1M|3M|6M|1Y|3Y|5Y|MAX)$"),  # noqa: A002
                  interval: str = Query("5m", pattern="^(1m|5m|15m|30m|1h|1D|1W|1M)$")):
    return quote.get_candles(_ticker(nse, bse, yt), range, interval)


@app.get("/api/projection")
def stock_projection(nse: Optional[str] = None, bse: Optional[str] = None, yt: Optional[str] = None,
                     demo: bool = False):
    return quote.get_projection(None if demo else _ticker(nse, bse, yt), demo)


# ---------------------------------------------------------------- search
@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=60)):
    q = q.strip()
    out: list[dict] = []
    if len(q) >= 2:
        out = market._cached(f"search:{q.lower()}", 3600, lambda: fast_search.search(q))
    ql = q.lower()
    if len(ql) >= 2 and ("demo".startswith(ql) or ql.startswith("demo")):
        out.append({"name": "Demo Industries Ltd (SYNTHETIC)", "demo": True, "nse_symbol": "DEMOIND"})
    return {"query": q, "results": out}


# ---------------------------------------------------------------- lazy report tabs
def _company(name, nse, bse, yt, scr, demo) -> dict:
    c = {"name": name or nse or bse or yt, "nse_symbol": nse, "bse_code": bse, "yahoo_ticker": yt,
         "screener_url": scr, "demo": demo}
    if not demo and not (nse or bse or yt):
        raise HTTPException(400, "Pick a company from the search suggestions")
    return c


@app.get("/api/stock/summary")
def stock_summary(name: Optional[str] = None, nse: Optional[str] = None, bse: Optional[str] = None,
                  yt: Optional[str] = None, scr: Optional[str] = None, demo: bool = False, refresh: bool = False):
    return reports.summary(_company(name, nse, bse, yt, scr, demo), refresh)


@app.get("/api/stock/section/{tab}")
def stock_section(tab: str, name: Optional[str] = None, nse: Optional[str] = None, bse: Optional[str] = None,
                  yt: Optional[str] = None, scr: Optional[str] = None, demo: bool = False):
    try:
        return reports.section(_company(name, nse, bse, yt, scr, demo), tab)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown tab {tab}") from exc


# ---------------------------------------------------------------- portfolio, watchlist, alerts
class HoldingIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    name: Optional[str] = Field(None, max_length=120)
    qty: float = Field(..., gt=0)
    avg_price: float = Field(..., gt=0)
    buy_date: Optional[str] = Field(None, max_length=10)


class WatchIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    name: Optional[str] = Field(None, max_length=120)
    alert_above: Optional[float] = Field(None, gt=0)
    alert_below: Optional[float] = Field(None, gt=0)
    note: Optional[str] = Field(None, max_length=300)


@app.get("/api/portfolio", dependencies=[Depends(portfolio_on)])
def portfolio_get():
    return portfolio.get_portfolio()


@app.post("/api/portfolio/holdings", dependencies=[Depends(portfolio_on)])
def portfolio_add(h: HoldingIn):
    try:
        return portfolio.add_holding(h.symbol, h.name, h.qty, h.avg_price, h.buy_date)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/portfolio/holdings/{hid}", dependencies=[Depends(portfolio_on)])
def portfolio_delete(hid: int):
    if not portfolio.delete_holding(hid):
        raise HTTPException(404, "Holding not found")
    return {"ok": True}


@app.get("/api/watchlist", dependencies=[Depends(portfolio_on)])
def watchlist_get():
    return portfolio.get_watchlist()


@app.post("/api/watchlist", dependencies=[Depends(portfolio_on)])
def watchlist_add(w: WatchIn):
    try:
        return portfolio.add_watch(w.symbol, w.name, w.alert_above, w.alert_below, w.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/watchlist/{symbol}", dependencies=[Depends(portfolio_on)])
def watchlist_delete(symbol: str):
    if not portfolio.delete_watch(symbol):
        raise HTTPException(404, "Not in watchlist")
    return {"ok": True}


@app.get("/api/alerts", dependencies=[Depends(portfolio_on)])
def alerts_get():
    return {"alerts": portfolio.recent_alerts(), "telegram": portfolio.telegram_configured()}


@app.post("/api/alerts/check", dependencies=[Depends(portfolio_on)])
def alerts_check():
    return {"fired": portfolio.check_alerts()}


@app.post("/api/alerts/test", dependencies=[Depends(portfolio_on)])
def alerts_test():
    if not portfolio.telegram_configured():
        raise HTTPException(400, "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, then restart the server")
    if not portfolio.send_telegram("✅ Stock Analyzer is connected. Your price alerts will arrive here."):
        raise HTTPException(502, "Telegram did not accept the message. Check the token and chat id.")
    return {"ok": True}


@app.on_event("startup")
def _start_alerts():
    if PORTFOLIO_ENABLED:
        portfolio.start_alert_worker()


# ---------------------------------------------------------------- news
@app.get("/api/news")
def market_news(category: str = Query("markets", pattern="^(all|markets|stocks|ipo|economy)$"),
                limit: int = Query(40, ge=1, le=100)):
    return news.get_news(category, limit)


@app.get("/api/news/company")
def stock_news(name: str = Query(..., min_length=1, max_length=120), symbol: Optional[str] = Query(None, max_length=30),
               limit: int = Query(20, ge=1, le=50)):
    return news.company_news(name, symbol, limit)


# ---------------------------------------------------------------- AdSense ads.txt
@app.get("/ads.txt", include_in_schema=False)
def ads_txt():
    """Google requires /ads.txt on the site root. Set ADSENSE_PUB_ID=pub-XXXXXXXXXXXXXXXX."""
    pub = os.environ.get("ADSENSE_PUB_ID", "").strip().removeprefix("ca-")
    if not pub:
        raise HTTPException(404, "ADSENSE_PUB_ID not set")
    return PlainTextResponse(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")


# ---------------------------------------------------------------- frontend
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Unknown API endpoint")
        f = (DIST / full_path).resolve()
        if full_path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
