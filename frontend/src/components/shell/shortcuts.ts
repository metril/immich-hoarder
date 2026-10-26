import { useEffect, useRef } from "react";

export const isMac = () => /mac|iphone|ipad/i.test(navigator.platform);
export const modLabel = () => (isMac() ? "⌘" : "Ctrl");

export function isEditable(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.isContentEditable || t.getAttribute("contenteditable") === "true";
}

const MODIFIERS = new Set(["Shift", "Control", "Alt", "Meta"]);

/**
 * Keys: "mod+k", single keys ("?", "/", "n"), and two-key sequences ("g j", second key within 1 s).
 * Plain keys are ignored while typing in form fields; mod+ combos still fire.
 */
export function useShortcuts(map: Record<string, () => void>) {
  const ref = useRef(map);
  useEffect(() => {
    ref.current = map;
  });
  useEffect(() => {
    let pending: { key: string; at: number } | null = null;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing || MODIFIERS.has(e.key)) return;
      const m = ref.current;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const mod = isMac() ? e.metaKey : e.ctrlKey;
      if (mod && !e.altKey) {
        pending = null;
        const h = m[`mod+${key}`];
        if (h) {
          e.preventDefault();
          h();
        }
        return;
      }
      if (isEditable(e.target) || e.ctrlKey || e.metaKey || e.altKey) {
        pending = null;
        return;
      }
      const now = Date.now();
      if (pending && now - pending.at <= 1000) {
        const h = m[`${pending.key} ${key}`];
        pending = null;
        if (h) {
          e.preventDefault();
          h();
          return;
        }
      }
      pending = null;
      const h = m[e.key];
      if (h) {
        e.preventDefault();
        h();
        return;
      }
      if (Object.keys(m).some((k) => k.startsWith(`${key} `))) pending = { key, at: now };
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
