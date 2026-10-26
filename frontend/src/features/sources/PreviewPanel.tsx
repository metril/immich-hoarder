import { useEffect, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "../../api/client";
import { ApiError, unwrap } from "../../api/errors";
import { type SourceIn } from "./hooks";

/** Dry run: POST /sources/preview with limit 50. The request is aborted when the panel unmounts. */
export function PreviewPanel({ draft }: { draft: SourceIn }) {
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => () => ctl.current?.abort(), []);
  const m = useMutation({
    mutationFn: async () => {
      ctl.current?.abort();
      const c = new AbortController();
      ctl.current = c;
      return unwrap(await api.POST("/api/v1/sources/preview", { body: { ...draft, limit: 50 }, signal: c.signal }));
    },
  });
  const busy = m.error instanceof ApiError && (m.error.status === 429 || m.error.status === 503);
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={m.isPending}
          onClick={() => m.mutate()}
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
        >
          Dry run
        </button>
        {m.isPending && (
          <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Running gallery-dl (up to 60 s)…
          </span>
        )}
      </div>
      {m.isError && (
        <p role="alert" className="text-sm text-destructive">
          {m.error.message}
          {busy && " The preview service is busy; try again shortly."}
        </p>
      )}
      {m.data &&
        (m.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No items found.</p>
        ) : (
          <ul aria-label="Preview results" className="grid max-h-96 gap-2 overflow-auto">
            {m.data.items.map((it, i) => (
              <li key={`${it.url}-${i}`} className="grid gap-0.5 rounded-md border p-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate font-medium" title={it.title ?? it.filename}>{it.title ?? it.filename}</span>
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${it.verdict === null ? "bg-secondary text-secondary-foreground" : "bg-muted text-foreground"}`}
                  >
                    {it.verdict === null ? "would grab" : it.verdict}
                  </span>
                </div>
                <span className="truncate text-xs text-muted-foreground" title={it.url}>{it.url}</span>
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
