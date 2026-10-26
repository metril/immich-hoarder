import { useEffect } from "react";
import { TriangleAlert } from "lucide-react";
import { Button } from "../ui/button";
import { CHUNK_RE, reloadOnce } from "./reload";

export function RouteError({ error, reset }: { error: unknown; reset: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  const chunk = CHUNK_RE.test(message);
  useEffect(() => {
    if (chunk) reloadOnce();
  }, [chunk, error]);
  return (
    <div role="alert" className="mx-auto max-w-md space-y-4 p-8 text-center">
      <TriangleAlert className="mx-auto size-8 text-warning" aria-hidden />
      <h2 className="font-display text-lg font-semibold">{chunk ? "A new version is available" : "Something went wrong"}</h2>
      <p className="text-sm text-muted-foreground break-words">{message}</p>
      <Button variant="outline" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
