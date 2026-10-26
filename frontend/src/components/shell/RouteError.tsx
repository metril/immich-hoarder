import { useEffect } from "react";
import { CHUNK_RE, reloadOnce } from "./reload";

export function RouteError({ error, reset }: { error: unknown; reset: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  const chunk = CHUNK_RE.test(message);
  useEffect(() => {
    if (chunk) reloadOnce();
  }, [chunk, error]);
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
