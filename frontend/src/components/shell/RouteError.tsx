import { useEffect } from "react";
import { pageReload } from "./reload";

const CHUNK_RE = /Failed to fetch dynamically imported module|Importing a module script failed/;
const FLAG = "ih-reloaded";

function shouldReload(error: unknown): boolean {
  if (!CHUNK_RE.test(error instanceof Error ? error.message : String(error))) return false;
  try {
    if (sessionStorage.getItem(FLAG)) return false;
    sessionStorage.setItem(FLAG, "1");
  } catch {
    return false;
  }
  return true;
}

export function RouteError({ error, reset }: { error: unknown; reset: () => void }) {
  const chunk = CHUNK_RE.test(error instanceof Error ? error.message : String(error));
  useEffect(() => {
    if (shouldReload(error)) pageReload.reload();
  }, [error]);
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="mx-auto max-w-md space-y-3 p-6 text-center">
      <h2 className="text-lg font-semibold">{chunk ? "A new version is available" : "Something went wrong"}</h2>
      <p className="text-sm text-muted-foreground break-words">{message}</p>
      <button
        type="button"
        onClick={reset}
        className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
      >
        Retry
      </button>
    </div>
  );
}
