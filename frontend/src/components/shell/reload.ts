/** Indirection so tests can observe reloads (jsdom's location.reload is not mockable). */
export const pageReload = { reload: () => location.reload() };

export const CHUNK_RE = /Failed to fetch dynamically imported module|Importing a module script failed/;
const FLAG = "ih-reloaded";

/** Reload the page at most once per session (stale hashed chunk after a deploy). */
export function reloadOnce(): boolean {
  try {
    if (sessionStorage.getItem(FLAG)) return false;
    sessionStorage.setItem(FLAG, "1");
  } catch {
    return false;
  }
  pageReload.reload();
  return true;
}

/** Vite fires this when a preloaded chunk 404s. Returns a disposer. */
export function installPreloadErrorGuard(): () => void {
  const on = () => void reloadOnce();
  window.addEventListener("vite:preloadError", on);
  return () => window.removeEventListener("vite:preloadError", on);
}
