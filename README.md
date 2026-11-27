# Indian Stock Analyzer – Fundamental Analysis & Valuation System

Type a company name or NSE symbol. The tool finds the company, pulls free public data (Yahoo Finance, Screener.in, NSE), calculates and explains the ratios in simple English, and writes two reports:

* **Excel workbook**: 14 formatted sheets with charts and conditional formatting.
* **Interactive HTML dashboard**: Plotly charts and tabs. It works offline and on mobile.

```
python main.py "Tata Motors"
python main.py "RELIANCE" --exchange NSE
python main.py "INFY" --periods 3M,6M,9M,1Y,3Y,5Y
python main.py --demo          # synthetic data, no internet needed
```

> **Not investment advice.** The tool describes past reported numbers. It never gives buy or sell calls.

---

## 1. Installation on Windows

1. Install **Python 3.11 or newer** from <https://www.python.org/downloads/>. During setup, tick **"Add python.exe to PATH"**.
2. Open **Command Prompt** (Win + R → `cmd`) and go to the project folder:
   ```bat
   cd C:\path\to\IndianStockAnalyzer
   ```
3. Create and activate a virtual environment (recommended):
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   ```
   On PowerShell, use `.venv\Scripts\Activate.ps1`. If it is blocked, run
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
4. Install the dependencies:
   ```bat
   pip install -r requirements.txt
   ```
5. Check that everything works without internet:
   ```bat
   python main.py --demo
   python -m pytest -q tests
   ```
6. Run a real analysis:
   ```bat
   python main.py "Tata Motors"
   ```

The reports are written to `output\` with a timestamp, for example `RELIANCE_analysis_20261118_203012.xlsx` and `RELIANCE_dashboard_20261118_203012.html`. Double-click the HTML file to open it in your browser.

On macOS or Linux, use `python3`, and `source .venv/bin/activate` to activate the environment.

## 2. Command-line options

| Option | Meaning |
|---|---|
| `"query"` | Company name, NSE symbol, BSE code (e.g. `500570`) or Yahoo ticker (`TCS.NS`) |
| `--exchange NSE\|BSE` | Preferred exchange when resolving a symbol |
| `--periods 3M,6M,1Y` | Which analysis periods to compute (default: all six) |
| `--peers N` | Maximum number of peers to analyse (`0` skips peers and runs faster) |
| `--choice N` | Picks candidate N automatically when a name is ambiguous (for scripts) |
| `--risk-free 6.4` | Risk-free rate in % for WACC (default 6.5, set in `config.py`) |
| `--erp 7.5` | Equity risk premium in % (default 7.0) |
| `--standalone` | Prefer standalone statements over consolidated |
| `--no-nse` | Do not call nseindia.com |
| `--plotly-cdn` | Smaller HTML file that loads Plotly from the internet when opened |
| `--demo` | Synthetic demo data with a clear "SYNTHETIC DEMO DATA" banner |
| `-v` | Verbose console logging |

If more than one company matches a name, the tool lists the matches and asks you to pick one. It never silently picks an unrelated company.

## 3. Data sources and how they are combined

| Dataset | Primary source | Fallback |
|---|---|---|
| CMP, 10-year price history, beta | Yahoo Finance (`yfinance`) | NSE quote, then Screener top ratios |
| Financial statements | Screener.in (consolidated preferred; ~10 years annual, ~13 quarters) | Yahoo Finance (~4 years) |
| Shareholding (promoter / FII / DII / public) | Screener.in quarterly pattern | NSE shareholding master |
| Promoter pledge | NSE pledge data | none: reported as unavailable |
| Peers | Screener.in peer list | Configured list in `config.py` |

Rules the tool follows:

* Each dataset comes from **one** primary source. Statements are never mixed across providers. Yahoo can only fill line items that Screener does not show (cash, capex), and only for the **same period-end** on a consolidated basis. Every such fill is listed in *Data Sources → Line-item derivations*.
* Missing values are shown as "—" or "Unavailable". They are **never** treated as zero and never interpolated.
* Rate limiting and caching are built in: at least 1.5 s between requests to the same site, and responses cached in `cache/` for 4–24 hours. Transient errors are retried up to 3 times. A site that cannot be reached is skipped for the rest of the run.
* The tool does **not** bypass CAPTCHA, logins or anti-bot protection. If a site refuses access, the dataset is marked *Restricted* and the analysis continues with what is available.

To add a provider, create a class in `data_providers/` with the same methods (`search`, statements, quote) and register it in `provider_manager.py`.

## 4. Definitions used

| Metric | Formula |
|---|---|
| EBITDA | EBIT + Depreciation & amortisation (EBIT = PBT + Finance cost when not reported) |
| EPS | As reported (net profit to shareholders / weighted shares). TTM = sum of the last 4 quarters |
| ROE | Net profit / **average** shareholders' equity × 100 |
| ROCE | EBIT / average capital employed × 100. Capital employed = Total assets − Current liabilities when reported, otherwise Equity + Borrowings. One definition per company, stated in the report |
| P/E | CMP / trailing EPS. Historical P/E = FY-end price / that year's EPS |
| PEG | P/E / 3-year EPS CAGR. *Not meaningful* if growth ≤ 0 |
| Debt/Equity | Total borrowings / Shareholders' equity |
| ROIC | NOPAT / average invested capital. NOPAT = EBIT × (1 − effective tax). Invested capital = Equity + Debt − Excess cash (cash above 2% of revenue) |
| WACC | E/(D+E)·Ke + D/(D+E)·Kd·(1−t). Ke = Rf + β·ERP. Kd = Interest / average debt. β is computed from 3 years of weekly returns against NIFTY 50 |
| Interest coverage | EBIT / Interest expense, with sector-adjusted thresholds |
| FCF | Cash from operations − Capex. Cash conversion = CFO / Net profit |

**Periods:**

* **3M / 6M / 9M** compare the last 1, 2 or 3 quarters with the same quarters one year earlier. This avoids seasonal distortion.
* **1Y** compares the trailing 4 quarters with the previous 4.
* **3Y / 5Y** use CAGR from annual statements.
* Historical ratios always come from the statements of those years.

**Banks, NBFCs and insurers:**

* ROCE, ROIC, D/E, interest coverage and EBITDA are marked *Not meaningful*.
* Instead the tool uses ROA, ROE versus cost of equity, and GNPA/NNPA (when Screener shows them).
* CAR, CASA and NIM are not available from free sources. They are listed as missing.

**Score out of 100:**

* 7 weighted categories, each with a published rubric (see the *Risk Assessment* sheet).
* A category with no data is excluded, and the other weights are scaled up so they still total 100. The coverage % is shown.
* Critical flags force the label to *High financial risk*. These are interest coverage below 1 and negative equity.

## 5. Project structure

```
main.py                 CLI and pipeline (resolve → retrieve → validate → calculate → explain → charts → Excel → HTML)
config.py               All assumptions, thresholds, weights, fallback peers
data_providers/         yahoo_provider, screener_provider, nse_provider, provider_manager, demo_provider, models
analysis/               price, period, fundamental_ratios, valuation, debt, interest_coverage, roic_wacc,
                        cashflow, promoter, peer, scoring_engine, explanation_engine, runner
reporting/              excel_report, html_report, charts, tables
utils/                  logger, financial_utils (safe maths + Metric record), data_validation, http_client (retry/cache)
templates/dashboard.html
tests/                  unit tests (offline)
output/  logs/  cache/
```

Every calculated metric keeps its source values, formula, period, result, data source and status (Actual, Derived, Estimate, Unavailable or Not meaningful). This shows on the *Fundamental Ratios* sheet.

## 6. Troubleshooting

| Problem | What to do |
|---|---|
| `Could not reach the data sources` | Check your internet connection. A corporate proxy or firewall may block finance sites, so try a home network. Details are in `logs\analyzer.log`. |
| `No Indian listed company found` | Try the NSE symbol (`TATAMOTORS`), the Yahoo ticker (`TATAMOTORS.NS`) or the BSE code (`500570`). Company names change after demergers, so check the current symbol on nseindia.com. |
| Yahoo returns nothing or "Too Many Requests" | Yahoo rate-limits by IP address. Wait 10–15 minutes. Run `pip install -U yfinance` (Yahoo changes its API often). |
| Screener shows "Restricted" (HTTP 403/429) | You have hit Screener's rate limit. Wait and retry. Cached pages are reused for 24 h. The tool falls back to Yahoo statements, which cover fewer years. |
| NSE data "Restricted" | NSE often blocks scripted access. Pledge and ISIN will show as unavailable, and everything else still works. Use `--no-nse` to skip it. |
| Few years of history / 5Y shows "—" | The statements came from Yahoo (~4 years). The report says so. Retry later when Screener is reachable. |
| `₹` shows as `?` in Command Prompt | Run `chcp 65001` first, or use Windows Terminal. The reports themselves are always correct. |
| Excel says "repaired records" | Close any older copy of the file that is open, and re-run. Each run creates a new, uniquely named file. |
| Stale data | Delete the `cache\` folder to force fresh downloads. |
| PowerShell won't activate the venv | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError` | Activate the venv, then `pip install -r requirements.txt`. |

## 7. Tests

```bat
python -m pytest -q tests
```

The tests check hand-computed values for ROE, ROCE, ROIC, WACC, interest coverage, P/E, PEG, EV/EBITDA and CAGR. They also cover:

* edge cases: negative EPS and equity, zero or missing interest, banks
* Screener HTML parsing
* company resolution and ambiguity handling
* merging data from providers without mixing sources
* score re-weighting
* full Excel and HTML generation

All tests run offline.

## 8. Sample report

`sample_reports/` holds an Excel file and an HTML dashboard built from **synthetic demo data** ("Demo Industries Ltd (SYNTHETIC)"). They show the layout only and do not describe any real company.

## 9. Web app: portfolio, watchlist, alerts and ads

Run the web app with `python -m uvicorn server.app:app --port 8000` and open <http://localhost:8000>.

* **Portfolio** (`/portfolio`): add each buy (stock, quantity, price, date). Buys of the same stock are combined at their average price. Shows live value, total and today's P&L, and allocation.
* **Watchlist & alerts** (`/portfolio?tab=watch`): set "above" and "below" price levels. The server checks them every 2 minutes. Each level fires once and is then cleared. Use the **☆ Add to watchlist** button on any stock page.
* Data is stored in `data/portfolio.db` (SQLite, single user for now).

**Telegram alerts (optional):**

1. In Telegram, message **@BotFather**, send `/newbot` and copy the token.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
3. Set the variables in PowerShell, then start the server:

   ```powershell
   $env:TELEGRAM_BOT_TOKEN="123:ABC"; $env:TELEGRAM_CHAT_ID="987654321"
   ```

4. Click **Send Telegram test** on the watchlist page.

**Google AdSense:**

1. Copy `frontend/.env.example` to `frontend/.env` and fill in your publisher id and ad unit ids.
2. Rebuild with `npm --prefix frontend run build`.
3. Set `$env:ADSENSE_PUB_ID="pub-XXXXXXXXXXXXXXXX"` so the server serves `/ads.txt`.

Ads appear on the home, stock report and portfolio pages. Without ids, nothing is shown (dev mode shows a placeholder box). `frontend/src/subscription.js` holds the plan switch: when a subscription is added, Pro users get `"pro"` and ads disappear for them.
