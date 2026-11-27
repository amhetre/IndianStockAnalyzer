// Cloudflare Worker in front of the app container (see wrangler.jsonc and DEPLOY.md).
//
// Every request goes to one shared container instance ("main"), which runs the
// Dockerfile image: FastAPI on port 8000 serving both the API and the React site.
// The container sleeps after INACTIVITY_MS without traffic and starts again on the
// next request (cold start takes a few seconds).
import { DurableObject } from "cloudflare:workers";

const PORT = 8000;
const INACTIVITY_MS = 15 * 60 * 1000;
const BOOT_TIMEOUT_MS = 120 * 1000;

// Worker variables / secrets passed through to the Python app as environment variables.
const PASS_THROUGH = [
  "ISA_ENABLE_PORTFOLIO", "ISA_CORS_ORIGINS", "ISA_RISK_FREE", "ISA_ERP",
  "ADSENSE_PUB_ID", "ADSENSE_CLIENT", "ADSENSE_SLOT_HOME", "ADSENSE_SLOT_REPORT", "ADSENSE_SLOT_PORTFOLIO",
  "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class StockAnalyzerContainer extends DurableObject {
  booting = null;

  containerEnv() {
    const out = { PORT: String(PORT) };
    for (const k of PASS_THROUGH) {
      const v = this.env[k];
      if (typeof v === "string" && v !== "") out[k] = v;
    }
    return out;
  }

  async ensureRunning() {
    const c = this.ctx.container;
    if (c.running && !this.booting) return;
    this.booting ||= (async () => {
      if (!c.running) {
        const opts = { enableInternet: true, env: this.containerEnv() }; // the app needs Yahoo, NSE and news feeds
        if (c.images?.base) opts.image = c.images.base;
        c.start(opts);
        c.monitor().catch((err) => console.error("container exited", err));
      }
      c.setInactivityTimeout?.(INACTIVITY_MS);
      // "running" is true before the server listens, so wait for the health check.
      const deadline = Date.now() + BOOT_TIMEOUT_MS;
      for (;;) {
        try {
          const r = await c.getTcpPort(PORT).fetch("http://container/api/health");
          if (r.ok) return;
        } catch { /* not listening yet */ }
        if (Date.now() > deadline) throw new Error("App container did not become healthy in time");
        await sleep(1000);
      }
    })().finally(() => { this.booting = null; });
    await this.booting;
  }

  async fetch(request) {
    try {
      await this.ensureRunning();
      return await this.ctx.container.getTcpPort(PORT).fetch(request);
    } catch (err) {
      console.error(err);
      return new Response("The app is starting up. Please refresh in a few seconds.", {
        status: 503, headers: { "Retry-After": "5", "Content-Type": "text/plain; charset=utf-8" },
      });
    }
  }
}

export default {
  async fetch(request, env) {
    const stub = env.APP.get(env.APP.idFromName("main"));
    return stub.fetch(request);
  },
};
