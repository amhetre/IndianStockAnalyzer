import { useEffect, useRef } from "react";
import { isPro } from "../subscription.js";

// Google AdSense, configured in frontend/.env (see .env.example):
//   VITE_ADSENSE_CLIENT=ca-pub-XXXXXXXXXXXXXXXX
//   VITE_ADSENSE_SLOT_HOME / _REPORT / _PORTFOLIO = ad unit ids from the AdSense dashboard
// Without a client id nothing is rendered in production; dev shows a placeholder box.
// Pro subscribers never see ads.

const CLIENT = import.meta.env.VITE_ADSENSE_CLIENT;
const SLOTS = {
  home: import.meta.env.VITE_ADSENSE_SLOT_HOME,
  report: import.meta.env.VITE_ADSENSE_SLOT_REPORT,
  portfolio: import.meta.env.VITE_ADSENSE_SLOT_PORTFOLIO,
};

let scriptAdded = false;
function loadScript() {
  if (scriptAdded || !CLIENT) return;
  scriptAdded = true;
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${CLIENT}`;
  s.crossOrigin = "anonymous";
  document.head.appendChild(s);
}

export default function AdSlot({ slot }) {
  const ref = useRef(null);
  const id = SLOTS[slot];
  const enabled = !isPro() && CLIENT && id;

  useEffect(() => {
    if (!enabled || ref.current?.dataset.pushed) return;
    loadScript();
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
      ref.current.dataset.pushed = "1";
    } catch { /* ad blocked or script not ready */ }
  }, [enabled]);

  if (isPro()) return null;
  if (!enabled) {
    return import.meta.env.DEV
      ? <div className="ad-slot"><div className="ad-placeholder">Ad space · “{slot}” (set VITE_ADSENSE_* in frontend/.env)</div></div>
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
