import { useEffect, useRef } from "react";
import { useConfig } from "../config.js";
import { isPro } from "../subscription.js";

// Google AdSense. Configured on the server at runtime (environment variables
// ADSENSE_CLIENT or ADSENSE_PUB_ID, and ADSENSE_SLOT_HOME / _REPORT / _PORTFOLIO;
// see DEPLOY.md), delivered through /api/config. For local frontend development the
// VITE_ADSENSE_* values in frontend/.env are used as a fallback.
// Without a client id nothing is rendered in production; dev shows a placeholder box.
// Pro subscribers never see ads.

const BUILD = {
  client: import.meta.env.VITE_ADSENSE_CLIENT,
  slots: {
    home: import.meta.env.VITE_ADSENSE_SLOT_HOME,
    report: import.meta.env.VITE_ADSENSE_SLOT_REPORT,
    portfolio: import.meta.env.VITE_ADSENSE_SLOT_PORTFOLIO,
  },
};

let scriptAdded = false;
function loadScript(client) {
  if (scriptAdded || !client) return;
  scriptAdded = true;
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  s.crossOrigin = "anonymous";
  document.head.appendChild(s);
}

export default function AdSlot({ slot }) {
  const ref = useRef(null);
  const cfg = useConfig();
  const ads = cfg?.adsense || (BUILD.client ? BUILD : null);
  const CLIENT = ads?.client;
  const id = ads?.slots?.[slot];
  const enabled = !isPro() && CLIENT && id;

  useEffect(() => {
    if (!enabled || ref.current?.dataset.pushed) return;
    loadScript(CLIENT);
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
      ref.current.dataset.pushed = "1";
    } catch { /* ad blocked or script not ready */ }
  }, [enabled]);

  if (isPro()) return null;
  if (!enabled) {
    return import.meta.env.DEV
      ? <div className="ad-slot"><div className="ad-placeholder">Ad space · “{slot}” (set ADSENSE_* on the server)</div></div>
      : null;
  }
  return (
    <div className="ad-slot">
      <span className="ad-label">Advertisement</span>
      <ins ref={ref} className="adsbygoogle" style={{ display: "block" }}
        data-ad-client={CLIENT} data-ad-slot={id} data-ad-format="auto" data-full-width-responsive="true" />
    </div>
  );
}
