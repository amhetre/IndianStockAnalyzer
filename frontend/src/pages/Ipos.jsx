import { useEffect, useState } from "react";
import { api } from "../api.js";
import AdSlot from "../components/AdSlot.jsx";
import IpoPanel from "../components/IpoPanel.jsx";

export default function Ipos() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    document.title = "IPOs · Stock Analyzer";
    api.ipos().then(setData).catch((e) => setErr(e.message));
  }, []);
  return (
    <div>
      <div className="page-head">
        <h1>IPOs: open and upcoming</h1>
        <p>Mainboard and SME issues on NSE and BSE, with subscription and grey-market premium (unofficial).</p>
      </div>
      <div style={{ marginTop: 14 }}><IpoPanel data={data} error={err} /></div>
      <AdSlot slot="home" />
    </div>
  );
}
