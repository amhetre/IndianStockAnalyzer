# Deploying to Cloudflare

Cloudflare pulls this repository from GitHub, builds the `Dockerfile`, and runs it as a
**Cloudflare Container** behind a small Worker (`cloudflare/worker.js`). Every push to
`main` rebuilds and redeploys automatically.

```
Browser ──► Cloudflare Worker (cloudflare/worker.js)
                 └─► Container: Docker image from ./Dockerfile
                        FastAPI on :8000 → /api/* + the React site
```

## What you need

* A Cloudflare account on the **Workers Paid** plan ($5 per month). Containers are not available on the free plan.
* This repository on GitHub (it is: `amhetre/IndianStockAnalyzer`).

## One-time setup

1. In the Cloudflare dashboard, open **Workers & Pages → Create application → Import a repository**.
2. Connect GitHub and pick **IndianStockAnalyzer**.
3. Use these settings:

   | Setting | Value |
   |---|---|
   | Project name | `indian-stock-analyzer` (must match `name` in `wrangler.jsonc`) |
   | Production branch | `main` |
   | Build command | *(leave empty)* |
   | Deploy command | `npx wrangler deploy` |
   | Root directory | `/` |

4. Click **Save and Deploy**. The first build takes a few minutes, because it builds the Docker image and pushes it to Cloudflare.
5. Open the `*.workers.dev` URL shown when the build finishes. The first visit can take 10–30 seconds while the container starts.

**Custom domain:** go to **Settings → Domains & Routes → Add → Custom domain**, and enter, for example, `stocks.yourdomain.in`. The domain's DNS must be on Cloudflare.

## Settings (Settings → Variables and Secrets)

The Worker passes these to the app. Change them in the dashboard. No rebuild is needed: the
container picks them up the next time it starts. To restart it now, redeploy or wait for it to sleep.

| Name | Type | Purpose |
|---|---|---|
| `ISA_ENABLE_PORTFOLIO` | Text | `false` (default in `wrangler.jsonc`). Keep it off until user accounts exist; otherwise every visitor shares one portfolio. |
| `ADSENSE_PUB_ID` | Text | e.g. `pub-1234567890123456`. Enables `/ads.txt` and the ad script. |
| `ADSENSE_SLOT_HOME` / `ADSENSE_SLOT_REPORT` / `ADSENSE_SLOT_PORTFOLIO` | Text | Ad unit ids from AdSense → Ads → By ad unit. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | **Secret** | Price alerts to Telegram (only with portfolio on). |
| `ISA_RISK_FREE`, `ISA_ERP` | Text | WACC assumptions, e.g. `0.065` and `0.07`. |
| `ISA_CORS_ORIGINS` | Text | Only if another domain calls the API. |

A plain text variable set in `wrangler.jsonc` (`vars`) is overwritten by the next deploy. Set your own values in the dashboard as **secrets**, or edit `wrangler.jsonc` and push.

## How it behaves

* **One container instance** serves everyone (`instance_type: "basic"`: 1/4 vCPU, 1 GiB RAM). If reports feel slow under load, change it to `"standard-1"` (1/2 vCPU, 4 GiB) in `wrangler.jsonc` and push.
* **Sleep:** after 15 minutes without visitors the container stops, and the next visit starts it again. Change `INACTIVITY_MS` in `cloudflare/worker.js`.
* **Storage is temporary:** the container disk resets on every restart and deploy. Caches simply refill. This is also why portfolio and watchlist are off: their database would be wiped. Accounts will need a real database (for example Cloudflare D1, or Postgres).
* **Logs:** dashboard → your Worker → **Logs** (observability is enabled in `wrangler.jsonc`).

### Rough cost

Paid plan $5/month includes 25 GiB-hours of memory and 375 vCPU-minutes per month.
A 1 GiB container that runs 24×7 uses about 730 GiB-hours, roughly $6–7 extra per month,
plus CPU while it is busy. With the 15-minute sleep and modest traffic it is usually much less.
Check current prices at <https://developers.cloudflare.com/containers/platform/pricing/>.

## Check before pushing

```powershell
npm install
npx wrangler deploy --dry-run
```

This needs Docker Desktop running. It validates `wrangler.jsonc`, builds the image and bundles the Worker without deploying.
(`wrangler dev` with containers does not run on Windows; use WSL for that, or test the image directly as below.)

## Run the same image anywhere else

The `Dockerfile` is a normal image, so it also runs on a VPS, Render, Railway or Fly.io:

```powershell
docker build -t stock-analyzer .
docker run -d -p 8000:8000 -e ISA_ENABLE_PORTFOLIO=false --name stock-analyzer stock-analyzer
```

The app listens on `$PORT` (default 8000) and has a health check at `/api/health`.
To keep data on a VPS, mount volumes on `/app/data` and `/app/cache`.
