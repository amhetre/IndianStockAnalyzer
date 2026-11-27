"""
IPO detail page: business, sector, size category, issue structure, objects of
the issue (why the money is raised / where it goes), financials, KPIs, peers,
promoters, anchor investors, lead managers, registrar and offer documents.

Parsed from the public IPO page on ipowatch.in. Section parsing is driven by
headings so that small layout changes or missing sections degrade gracefully.
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from server.market import _cached
from utils.http_client import AccessRestricted, FetchError, HttpClient
from utils.logger import get_logger

log = get_logger("server.ipo_detail")

BASE = "https://ipowatch.in"
SOURCE = "IPO Watch (ipowatch.in)"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,150}$")
_http = HttpClient()

# SEBI/AMFI-style size buckets by full market capitalisation (approximate, ₹ crore).
LARGE_CAP_CR = 100_000
MID_CAP_CR = 33_000


class IpoNotFound(Exception):
    pass


def _num(text) -> Optional[float]:
    if text is None:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(text))
    return float(m.group(0).replace(",", "")) if m else None


def _table(t) -> list[list[str]]:
    return [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in t.find_all("tr")]


def _kv(rows: list[list[str]]) -> dict:
    return {r[0]: r[1] for r in rows if len(r) >= 2 and r[0]}


def _clean_li(text: str) -> str:
    return re.sub(r"^\s*\d{1,2}\s+", "", text).strip()


def _sections(content) -> dict[str, list]:
    """Group p/ul/ol/table elements under their nearest preceding h2/h3 heading."""
    out: dict[str, list] = {}
    current = "_top"
    for el in content.find_all(["h2", "h3", "p", "ul", "ol", "table"]):
        if el.name in ("h2", "h3"):
            current = el.get_text(" ", strip=True)
            if current.lower().startswith(("frequently asked", "join the discussion", "lot size calculator")):
                break
            out.setdefault(current, [])
            continue
        # skip p/ul nested inside tables or lists we already capture
        if el.find_parent(["table", "li"]):
            continue
        out.setdefault(current, []).append(el)
    return out


def _find(sections: dict, *needles: str) -> list:
    for name, els in sections.items():
        low = name.lower()
        if any(n in low for n in needles):
            return els
    return []


def _paras(els) -> list[str]:
    return [e.get_text(" ", strip=True) for e in els if e.name == "p" and e.get_text(strip=True)]


def _lists(els) -> list[str]:
    items = []
    for e in els:
        if e.name in ("ul", "ol"):
            items += [_clean_li(li.get_text(" ", strip=True)) for li in e.find_all("li")]
    return [i for i in dict.fromkeys(items) if i]


def _tables(els) -> list[list[list[str]]]:
    return [_table(e) for e in els if e.name == "table"]


def _metadata(soup) -> dict:
    """Registrar / lead managers / market maker / contact blocks."""
    out: dict[str, list[dict]] = {}
    for grid in soup.select(".ipo-metadata-grid"):
        for block in grid.find_all("div", recursive=False):
            kids = block.find_all("div", recursive=False)
            if not kids:
                continue
            label = kids[0].get_text(" ", strip=True)
            entries = []
            for k in kids[1:]:
                a = k.find("a")
                href = a.get("href", "") if a else ""
                text = k.get_text(" ", strip=True)
                links = [x for x in k.find_all("a") if not (x.get("href") or "").startswith(("tel:", "mailto:"))]
                if href.startswith("tel:"):
                    entries.append({"phone": text})
                elif href.startswith("mailto:"):
                    entries.append({"email": text})
                elif len(links) > 1:  # several lead managers in one cell
                    entries += [{"name": x.get_text(" ", strip=True)} for x in links if x.get_text(strip=True)]
                elif k.find_all("div") and not a:
                    entries += [{"name": x.get_text(" ", strip=True)} for x in k.find_all("div")
                                if x.get_text(strip=True) and not x.find("div")]
                elif text:
                    entries.append({"name": text})
            if label and entries:
                out.setdefault(label, []).extend(entries)
    return out


def _people(meta: dict, *labels: str) -> list[dict]:
    """Collapse name/phone/email entries into one record per name."""
    res: list[dict] = []
    for lab, entries in meta.items():
        if not any(l in lab.lower() for l in labels):
            continue
        for e in entries:
            if "name" in e:
                res.append({"name": e["name"]})
            elif res:
                res[-1].update(e)
    return res


def _financials(rows: list[list[str]]) -> dict:
    if not rows or len(rows[0]) < 2:
        return {}
    periods = rows[0][1:]
    items = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        items.append({"label": r[0], "values": [_num(v) for v in r[1:len(periods) + 1]]})
    return {"periods": periods, "unit": "₹ crore", "rows": items}


def _get(fin: dict, *names: str) -> list[Optional[float]]:
    for row in fin.get("rows", []):
        if any(n in row["label"].lower() for n in names):
            return row["values"]
    return []


def _size_category(is_sme: bool, mcap_cr: Optional[float]) -> dict:
    if is_sme:
        return {"label": "SME", "note": "Listed on the SME platform (NSE Emerge / BSE SME): smaller companies, "
                                        "higher risk, lower liquidity and larger lot sizes."}
    if mcap_cr is None:
        return {"label": "Mainboard", "note": "Market cap could not be estimated."}
    if mcap_cr >= LARGE_CAP_CR:
        return {"label": "Large cap", "note": f"Estimated market cap ≥ ₹{LARGE_CAP_CR:,} Cr."}
    if mcap_cr >= MID_CAP_CR:
        return {"label": "Mid cap", "note": f"Estimated market cap between ₹{MID_CAP_CR:,} and ₹{LARGE_CAP_CR:,} Cr."}
    return {"label": "Small cap", "note": f"Estimated market cap below ₹{MID_CAP_CR:,} Cr."}


def parse(html: str, slug: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else slug
    name = re.sub(r"\s+IPO( Details)?$", "", title).strip()

    sub = soup.select_one(".ipo-detail__subtitle")
    sector = None
    listed_on = None
    if sub:
        a = sub.find("a", href=re.compile(r"/sectors/"))
        sector = a.get_text(strip=True) if a else None
        m = re.search(r"Listed on\s+([^·]+)", sub.get_text(" ", strip=True))
        listed_on = m.group(1).strip() if m else None
    chips = [c.get_text(strip=True) for c in soup.select(".ipo-chip")]
    board = next((c for c in chips if c.lower() in ("mainboard", "sme", "nse emerge", "bse sme")), None)
    status = next((c for c in chips if c not in (board,)), None)

    secs = _sections(soup)

    details = {}
    for t in _tables(_find(secs, "ipo details")):
        details.update(_kv(t))
    about_ipo = _paras(_find(secs, "about") and secs.get(next((k for k in secs if k.lower().startswith("about") and "ipo" in k.lower()), ""), []))
    about_company = _paras(next((v for k, v in secs.items() if k.lower() == "about company"), []))
    objects = _lists(_find(secs, "objects of the issue", "objects of issue"))
    if not objects:
        objects = _paras(_find(secs, "objects of the issue", "objects of issue"))

    fin_tables = _tables(_find(secs, "company financials", "financial"))
    financials = _financials(fin_tables[0]) if fin_tables else {}
    kpi = {}
    for t in _tables(_find(secs, "kpi", "valuation")):
        rows = [r for r in t if len(r) >= 2]
        if rows and rows[0][0].lower() == "kpi":
            rows = rows[1:]
        kpi.update({r[0]: r[-1] for r in rows})
    peers_t = _tables(_find(secs, "peer comparison", "peer"))
    peers = {"header": peers_t[0][0], "rows": peers_t[0][1:]} if peers_t and len(peers_t[0]) > 1 else None
    anchors_t = _tables(_find(secs, "anchor"))
    anchors = [r for r in anchors_t[0][1:] if len(r) >= 3] if anchors_t else []
    promo_els = _find(secs, "promoter")
    promoters_text = " ".join(_paras(promo_els))
    holding_t = _tables(promo_els)
    holding = {"header": holding_t[0][0], "rows": holding_t[0][1:]} if holding_t and len(holding_t[0]) > 1 else None
    strengths = _lists(_find(secs, "strength"))
    risks = _lists(_find(secs, "risk"))
    gmp_t = _tables(_find(secs, "gmp trend"))
    gmp_trend = [{"date": r[0], "gmp": _num(r[1]), "est_listing": _num(r[2]), "gain_pct": _num(r[3])}
                 for r in (gmp_t[0][1:] if gmp_t else []) if len(r) >= 4]
    subscription = None
    for t in _tables(_find(secs, "gmp trend", "subscription")):
        if t and t[0] and "subscription" in " ".join(t[0]).lower():
            subscription = {"header": t[0], "rows": t[1:]}
    reservation_t = _tables(_find(secs, "reservation"))
    reservation = {"header": reservation_t[0][0], "rows": reservation_t[0][1:]} if reservation_t else None
    lots_t = _tables(_find(secs, "lot size"))
    lots = {"header": lots_t[0][0], "rows": lots_t[0][1:]} if lots_t else None

    meta = _metadata(soup)
    registrar = _people(meta, "registrar")
    lead_managers = _people(meta, "lead manager", "book running")
    market_makers = _people(meta, "market maker")

    website = None
    docs = []
    for a in soup.find_all("a"):
        t = a.get_text(strip=True)
        href = a.get("href") or ""
        if t == "Visit Website" and href.startswith("http"):
            website = href
        elif t in ("DRHP", "RHP") and href.startswith("http"):
            docs.append({"label": t, "url": href})
    docs = list({d["label"]: d for d in docs}.values())

    contact = None
    for k, v in secs.items():
        if "contact" in k.lower():
            contact = " ".join(_paras(v)) or None

    # ---- derived figures
    price_band = details.get("Price Band") or details.get("Issue Price")
    upper = max([_num(x) for x in re.findall(r"[\d,]+(?:\.\d+)?", price_band or "")] or [0]) or None
    issue_size_cr = _num(details.get("Total Issue Size"))
    fresh_cr = _num(details.get("Fresh Issue"))
    ofs_cr = _num(details.get("Offer for Sale"))
    is_sme = (board or "").lower() in ("sme", "nse emerge", "bse sme") or "sme" in (details.get("Listing At") or "").lower()

    pe = _num(kpi.get("Price/Earning P/E Ratio") or kpi.get("P/E (x)") or kpi.get("P/E Ratio"))
    pat = [v for v in _get(financials, "profit after tax", "pat") if v is not None]
    periods = financials.get("periods", [])
    # Prefer the latest full financial year (31 Mar) for annual PAT; stub periods (e.g. 30 Jun) are partial.
    fy_pat = None
    for p, v in zip(periods, _get(financials, "profit after tax", "pat")):
        if v is not None and "mar" in p.lower():
            fy_pat = v
            break
    mcap_cr = None
    mcap_basis = None
    explicit = next((v for k, v in kpi.items() if "market cap" in k.lower()), None)
    if explicit:
        mcap_cr, mcap_basis = _num(explicit), "As stated in the offer document"
    elif pe and fy_pat and fy_pat > 0:
        mcap_cr, mcap_basis = round(pe * fy_pat, 0), "Estimated: issue P/E × latest full-year profit"
    borrow = _get(financials, "borrowing", "debt")
    networth = _get(financials, "net worth")
    reserves = _get(financials, "reserves")
    # Net worth must be ≥ reserves; skip periods where the source data is inconsistent.
    networth = [nw if nw is None or not (i < len(reserves) and reserves[i] and nw < reserves[i]) else None
                for i, nw in enumerate(networth)]

    return {
        "slug": slug, "source": SOURCE, "source_url": f"{BASE}/{slug}/",
        "name": name, "sector": sector, "listed_on": listed_on, "board": board or ("SME" if is_sme else "Mainboard"),
        "status": status, "is_sme": is_sme,
        "size": _size_category(is_sme, mcap_cr),
        "valuation": {
            "market_cap_cr": mcap_cr, "basis": mcap_basis, "pe": pe,
            "issue_size_cr": issue_size_cr, "fresh_issue_cr": fresh_cr, "ofs_cr": ofs_cr,
            "upper_price": upper,
            "latest_borrowing_cr": next((v for v in borrow if v is not None), None),
            "latest_net_worth_cr": next((v for v in networth if v is not None), None),
            "debt_to_equity": _num(kpi.get("Debt/Equity Ratio") or kpi.get("Debt/Equity")),
        },
        "about_ipo": about_ipo, "about_company": about_company,
        "details": details, "objects": objects,
        "financials": financials, "kpi": kpi, "peers": peers,
        "promoters": promoters_text, "holding": holding, "anchors": anchors,
        "strengths": strengths, "risks": risks,
        "gmp_trend": gmp_trend, "subscription": subscription, "reservation": reservation, "lots": lots,
        "registrar": registrar, "lead_managers": lead_managers, "market_makers": market_makers,
        "website": website, "documents": docs, "contact": contact,
    }


def get_detail(slug: str) -> dict:
    slug = slug.strip("/").lower()
    if not SLUG_RE.match(slug):
        raise IpoNotFound("Invalid IPO id")

    def produce():
        try:
            html = _http.get(f"{BASE}/{slug}/", ttl_hours=0.5)
        except (AccessRestricted, FetchError) as exc:
            raise IpoNotFound(f"IPO page unavailable: {exc}") from exc
        return parse(html, slug)
    return _cached(f"ipo:{slug}", 1800, produce)
