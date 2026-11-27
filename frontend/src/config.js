// Runtime feature switches from the server (GET /api/config), fetched once.
import { useEffect, useState } from "react";
import { api } from "./api.js";

let cached = null;
let pending = null;
const DEFAULTS = { portfolio: true };

function load() {
  pending ||= api.config().then((c) => (cached = { ...DEFAULTS, ...c })).catch(() => (cached = DEFAULTS));
  return pending;
}

export function useConfig() {
  const [cfg, setCfg] = useState(cached);
  useEffect(() => { if (!cached) load().then(setCfg); }, []);
  return cfg; // null while loading
}
