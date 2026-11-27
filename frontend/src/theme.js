// Global light / dark theme.
//
// - index.html applies the theme class before first paint (no flash).
// - A choice made with the toggle is saved in localStorage and wins on later visits.
// - Until the user chooses, the theme follows the operating-system setting, live.
// - Components that draw charts on canvas call useTheme() so they redraw on change;
//   everything else reads CSS variables and updates by itself.
import { useSyncExternalStore } from "react";

export const THEME_KEY = "isa.theme";
const EVENT = "isa:themechange";
const root = document.documentElement;
const media = window.matchMedia?.("(prefers-color-scheme: dark)");

function stored() {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

export const getTheme = () => (root.classList.contains("dark") ? "dark" : "light");

function apply(theme, animate) {
  if (theme === getTheme()) return;
  if (animate) {
    root.classList.add("theme-switching");
    clearTimeout(apply.t);
    apply.t = setTimeout(() => root.classList.remove("theme-switching"), 320);
  }
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", getComputedStyle(root).getPropertyValue("--sidebar").trim());
  window.dispatchEvent(new Event(EVENT));
}

export function setTheme(theme) {
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* storage blocked: still switch for this visit */ }
  apply(theme, true);
}

export const toggleTheme = () => setTheme(getTheme() === "dark" ? "light" : "dark");

// Follow the OS setting while the user has not picked a theme.
media?.addEventListener("change", (e) => { if (!stored()) apply(e.matches ? "dark" : "light", true); });

function subscribe(cb) {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}

export function useTheme() {
  return useSyncExternalStore(subscribe, getTheme);
}

// Resolved colour values of theme tokens, for canvas chart libraries that cannot read CSS variables.
export function themeTokens(...names) {
  const cs = getComputedStyle(root);
  return Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(`--${n}`).trim()]));
}
