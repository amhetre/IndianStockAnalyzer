import { useEffect, useRef, useState } from "react";
import { abbrCr, api } from "../api.js";
import { useTheme } from "../theme.js";

let plotlyP = null;
const getPlotly = () => (plotlyP ||= import("plotly.js-dist-min").then((m) => m.default || m));

// Plotly (Python ≥ 6) ships numeric arrays as {dtype, bdata: base64}
const TYPED = { f8: Float64Array, f4: Float32Array, i4: Int32Array, i2: Int16Array, i1: Int8Array, u4: Uint32Array, u2: Uint16Array, u1: Uint8Array };
function arr(y) {
  if (Array.isArray(y)) return y.map(Number);
  if (y?.bdata && TYPED[y.dtype]) {
    const b = Uint8Array.from(atob(y.bdata), (c) => c.charCodeAt(0));
    return Array.from(new TYPED[y.dtype](b.buffer));
  }
  return [];
}

function themed(fig) {
  const cs = getComputedStyle(document.documentElement);
  const v = (n) => cs.getPropertyValue(n).trim();
  const layout = { ...fig.layout, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { ...(fig.layout?.font || {}), color: v("--foreground") },
    hoverlabel: { bgcolor: v("--popover"), bordercolor: v("--border"), font: { color: v("--foreground") } },
    legend: { ...(fig.layout?.legend || {}), font: { ...(fig.layout?.legend?.font || {}), color: v("--muted-foreground") } } };
  for (const ax of Object.keys(layout).filter((k) => /^[xy]axis\d*$/.test(k))) {
    layout[ax] = { ...layout[ax], gridcolor: v("--chart-grid"), linecolor: v("--border"), zerolinecolor: v("--border"),
      tickfont: { ...(layout[ax]?.tickfont || {}), color: v("--muted-foreground") } };
  }
  // ₹ crore axes: Indian abbreviations (₹45K Cr, ₹4 L Cr) instead of Plotly's "400k"
  const yt = layout.yaxis?.title;
  if (/crore/i.test(typeof yt === "string" ? yt : yt?.text || "")) {
    const ys = (fig.data || []).flatMap((t) => arr(t.y)).filter((y) => Number.isFinite(y));
    if (ys.length) {
      const lo = Math.min(0, ...ys), hi = Math.max(0, ...ys);
      const raw = (hi - lo) / 5 || 1, mag = 10 ** Math.floor(Math.log10(raw));
      const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
      const vals = [];
      for (let t = Math.floor(lo / step) * step; t <= hi + step / 2; t += step) vals.push(+t.toFixed(6));
      layout.yaxis = { ...layout.yaxis, tickmode: "array", tickvals: vals, ticktext: vals.map((t) => abbrCr(t, { digits: 1 })) };
    }
  }
  if (layout.title && typeof layout.title === "object") layout.title = { ...layout.title, font: { ...(layout.title.font || {}), color: v("--text") } };
  return { data: fig.data, layout };
}

// One report tab. Data is requested only when the tab is first shown; results are kept by the parent.
export default function ReportSection({ company, tab, cached, onLoaded }) {
  const [state, setState] = useState(cached || { status: "loading", steps: [] });
  const [nonce, setNonce] = useState(0);
  const box = useRef(null);
  const theme = useTheme(); // Plotly charts are redrawn with the new colours on theme change

  useEffect(() => {
    if (cached?.status === "done") { setState(cached); return; }
    let alive = true, timer;
    setState({ status: "loading", steps: [] });
    const poll = () => api.section(company, tab).then((r) => {
      if (!alive) return;
      setState(r);
      if (r.status === "loading") timer = setTimeout(poll, 1500);
      else if (r.status === "done") onLoaded(tab, r);
    }).catch((e) => alive && setState({ status: "error", error: e.message }));
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [company, tab, nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  // Mount Plotly charts into the server-rendered placeholders
  useEffect(() => {
    if (state.status !== "done" || !box.current) return;
    const els = [...box.current.querySelectorAll(".pchart[data-fig]")];
    if (!els.length) return;
    let alive = true;
    getPlotly().then((Plotly) => {
      if (!alive) return;
      els.forEach((el) => {
        const f = state.figs?.[el.dataset.fig];
        if (f) { const t = themed(f); Plotly.newPlot(el, t.data, t.layout, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] }); }
      });
    });
    return () => { alive = false; getPlotly().then((P) => els.forEach((el) => { try { P.purge(el); } catch { /* gone */ } })); };
  }, [state, theme]);

  // Learn tab: research checklist progress
  useEffect(() => {
    const cl = box.current?.querySelector("#checklist");
    if (!cl) return;
    const boxes = [...cl.querySelectorAll("input[type=checkbox]")];
    const upd = () => {
      const n = boxes.filter((b) => b.checked).length;
      const p = boxes.length ? Math.round((n / boxes.length) * 100) : 0;
      const fill = box.current.querySelector("#cl-fill"), pct = box.current.querySelector("#cl-pct");
      if (fill) fill.style.width = p + "%";
      if (pct) pct.textContent = p + "%";
      boxes.forEach((b) => b.closest("li")?.classList.toggle("done", b.checked));
    };
    boxes.forEach((b) => b.addEventListener("change", upd));
    box.current.querySelector("#cl-reset")?.addEventListener("click", () => { boxes.forEach((b) => (b.checked = false)); upd(); });
    upd();
  }, [state]);

  if (state.status === "error") {
    return (
      <div className="card error-box big">
        <h3>Couldn't load this section</h3>
        <p>{state.error}</p>
        <button className="btn" onClick={() => setNonce((n) => n + 1)}>Try again</button>
      </div>
    );
  }
  if (state.status !== "done") {
    const steps = state.steps || [];
    return (
      <div className="card progress">
        <div className="progress-head">
          <span className="spinner" />
          <div>
            <h3>{tab === "peers" ? "Loading peer companies…" : "Fetching financial data…"}</h3>
            <p className="muted">
              {tab === "peers"
                ? "Each peer's statements are downloaded and analysed with the same rules. This can take a minute."
                : "Statements, shareholding and ratios are fetched the first time you open a report tab. Other tabs open instantly after this."}
            </p>
          </div>
        </div>
        <div className="progress-bar"><span style={{ width: `${Math.min(95, 10 + steps.length * 9)}%` }} /></div>
        <ol className="steps">
          {steps.slice(-6).map((s, i, a) => (
            <li key={i} className={i === a.length - 1 ? "current" : s.startsWith("!") ? "warn" : ""}>{s}</li>
          ))}
        </ol>
      </div>
    );
  }
  return <div ref={box} className="card rpt" dangerouslySetInnerHTML={{ __html: state.html }} />;
}
