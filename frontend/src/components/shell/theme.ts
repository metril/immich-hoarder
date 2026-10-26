import { useEffect, useSyncExternalStore } from "react";

export type Theme = "light" | "dark" | "system";
const KEY = "ih-theme";
const listeners = new Set<() => void>();
let current: Theme | null = null;

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* storage unavailable */
  }
  return "system";
}

const getTheme = (): Theme => (current ??= read());

export function applyTheme(t: Theme) {
  const dark = t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function setTheme(t: Theme) {
  current = t;
  try {
    localStorage.setItem(KEY, t);
  } catch {
    /* storage unavailable */
  }
  applyTheme(t);
  listeners.forEach((l) => l());
}

const onStorage = (e: StorageEvent) => {
  if (e.key !== null && e.key !== KEY) return;
  current = read();
  listeners.forEach((l) => l());
};

const subscribe = (l: () => void) => {
  if (listeners.size === 0) window.addEventListener("storage", onStorage);
  listeners.add(l);
  return () => {
    listeners.delete(l);
    if (listeners.size === 0) window.removeEventListener("storage", onStorage);
  };
};

export function useTheme() {
  // Re-read storage per mount so tests/other tabs' choice is honoured.
  const theme = useSyncExternalStore(subscribe, getTheme);
  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [theme]);
  return { theme, setTheme };
}

/** Test helper: forget the cached value so the next read hits storage. */
export function resetThemeCache() {
  current = null;
}
