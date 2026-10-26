import { useEffect, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "../../api/client";
import { ApiError, unwrap } from "../../api/errors";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Truncate } from "../../components/ui/truncate";
import { type SourceIn } from "./hooks";

export const PREVIEW_TIMEOUT_MS = 65_000;

/** Dry run: POST /sources/preview with limit 50. The request is aborted when the panel unmounts. */
export function PreviewPanel({ draft }: { draft: SourceIn }) {
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => () => ctl.current?.abort(), []);
  const m = useMutation({
    mutationFn: async () => {
      ctl.current?.abort();
      const c = new AbortController();
      ctl.current = c;
      return unwrap(await api.POST("/api/v1/sources/preview", { body: { ...draft, limit: 50 }, signal: AbortSignal.any([c.signal, AbortSignal.timeout(PREVIEW_TIMEOUT_MS)]) }));
    },
  });
  const timedOut = m.error instanceof DOMException && m.error.name === "TimeoutError";
  const busy = m.error instanceof ApiError && (m.error.status === 429 || m.error.status === 503);
  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-3">
        <Button loading={m.isPending} onClick={() => m.mutate()}>
          Dry run
        </Button>
        {m.isPending && (
          <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Running gallery-dl (up to 60 s)…
          </span>
        )}
      </div>
      {m.isError && (
        <p role="alert" className="text-sm text-destructive">
          {timedOut ? "Preview timed out" : m.error.message}
          {busy && " The preview service is busy; try again shortly."}
        </p>
      )}
      {m.data &&
        (m.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No items found.</p>
        ) : (
          <ul aria-label="Preview results" className="grid max-h-96 gap-3 overflow-auto">
            {m.data.items.map((it, i) => (
              <li key={`${it.url}-${i}`} className="grid gap-1.5 rounded-lg border p-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <Truncate className="font-medium">{it.title ?? it.filename}</Truncate>
                  <Badge tone={it.verdict === null ? "success" : "neutral"} className="shrink-0">
                    {it.verdict === null ? "would grab" : it.verdict}
                  </Badge>
                </div>
                <Truncate className="text-xs text-muted-foreground">{it.url}</Truncate>
                <span className="text-xs text-muted-foreground">
                  {it.filename}
                  {it.date ? ` · ${it.date}` : ""}
                </span>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
