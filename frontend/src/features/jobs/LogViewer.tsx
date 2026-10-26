import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { toast } from "sonner";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import type { LogLine } from "../../live/types";
import { MAX_LOG, useJobStream, type JobStreamState } from "../../live/useJobStream";
import { downloadLog } from "./downloadLog";
import { LEVELS, filterLog, normLevel, type Level } from "./logFilter";

const ROW_H = 20;
const btn = "inline-flex h-9 items-center rounded-md border px-3 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50";
const FIRST_PAGE = 200; // backend MAX_LIMIT (brief said 500; API rejects >200)

const LEVEL_CLASS: Record<string, string> = {
  error: "text-destructive",
  warn: "text-amber-600 dark:text-amber-400",
  debug: "text-muted-foreground",
  trace: "text-muted-foreground",
};

function highlight(text: string, q: string): ReactNode {
  const needle = q.trim();
  if (!needle) return text;
  const lower = text.toLowerCase();
  const n = needle.toLowerCase();
  const out: ReactNode[] = [];
  let i = 0;
  for (;;) {
    const j = lower.indexOf(n, i);
    if (j < 0) break;
    if (j > i) out.push(text.slice(i, j));
    out.push(<mark key={j}>{text.slice(j, j + n.length)}</mark>);
    i = j + n.length;
  }
  out.push(text.slice(i));
  return out;
}

function useDebounced<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

interface Props {
  jobId: number;
  live: boolean;
  /** Share the page's stream instead of opening a second one. */
  stream?: JobStreamState;
}

export function LogViewer(props: Props) {
  return props.stream ? <Viewer {...props} stream={props.stream} /> : <Owned {...props} />;
}

function Owned(props: Props) {
  const stream = useJobStream(props.jobId);
  return <Viewer {...props} stream={stream} />;
}

function Viewer({ jobId, live, stream }: Props & { stream: JobStreamState }) {
  const [level, setLevel] = useState<Level>("info");
  const [search, setSearch] = useState("");
  const query = useDebounced(search, 150);
  const [auto, setAuto] = useState(true);
  const [progress, setProgress] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const first = useQuery({
    queryKey: keys.jobEvents(jobId, level),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/jobs/{job_id}/events", {
          params: { path: { job_id: jobId }, query: { limit: FIRST_PAGE, min_level: level } },
        }),
      ),
  });

  // API page (reversed to ascending) is merged once per fetch.
  const base = useMemo(() => {
    const out: LogLine[] = [];
    for (const e of first.data?.items ?? []) {
      if (e.type !== "log") continue;
      const d = e.data as { msg?: unknown; logger?: unknown };
      out.push({
        type: "log",
        id: e.id,
        ts: e.ts,
        job_id: jobId,
        level: normLevel(e.level),
        msg: typeof d.msg === "string" ? d.msg : "",
        logger: typeof d.logger === "string" ? d.logger : undefined,
        data: e.data,
      });
    }
    out.sort((x, y) => x.id - y.id);
    return { lines: out, ids: new Set(out.map((l) => l.id)), max: out.at(-1)?.id ?? -1 };
  }, [first.data, jobId]);

  // Stream tail is appended without re-sorting the whole buffer.
  const { merged, overflow } = useMemo(() => {
    const tail: LogLine[] = [];
    let extra = false;
    for (const l of stream.log) {
      if (l.id > base.max) tail.push(l);
      else if (!base.ids.has(l.id)) {
        tail.push(l);
        extra = true;
      }
    }
    let all = base.lines.concat(tail);
    if (extra || tail.some((l, i) => i > 0 && l.id <= (tail[i - 1]?.id ?? -1))) {
      const seen = new Set<number>();
      all = all.filter((l) => !seen.has(l.id) && seen.add(l.id)).sort((x, y) => x.id - y.id);
    }
    return { merged: all.slice(-MAX_LOG), overflow: all.length > MAX_LOG };
  }, [base, stream.log]);

  const rows = useMemo(() => filterLog(merged, { minLevel: level, query }), [merged, level, query]);

  const countText = useDebounced(`${rows.length.toLocaleString()} lines`, 2000);

  // eslint-disable-next-line react-hooks/incompatible-library
  const v = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 10,
    initialRect: { width: 1024, height: 400 },
  });

  useEffect(() => {
    if (auto && rows.length > 0) v.scrollToIndex(rows.length - 1, { align: "end" });
  }, [auto, rows.length, v]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight > ROW_H * 2) setAuto(false);
  };

  const onDownload = async () => {
    const ac = new AbortController();
    abortRef.current = ac;
    setProgress(0);
    try {
      await downloadLog(jobId, level, { signal: ac.signal, onProgress: setProgress });
    } catch (e) {
      if (!ac.signal.aborted) toast.error(e instanceof Error ? e.message : "Download failed");
    } finally {
      abortRef.current = null;
      setProgress(null);
    }
  };

  return (
    <section aria-label="Job log" className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-sm">
          Level
          <select value={level} onChange={(e) => setLevel(e.target.value as Level)} className="h-9 rounded-md border bg-background px-2 text-sm">
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <input
          type="search"
          aria-label="Search log"
          placeholder="Search log"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 min-w-40 flex-1 rounded-md border bg-background px-2 text-sm"
        />
        <button type="button" className={btn} aria-pressed={auto} onClick={() => setAuto((a) => !a)}>
          Auto-scroll
        </button>
        {!auto && (
          <button type="button" className={btn} onClick={() => setAuto(true)}>
            Jump to latest
          </button>
        )}
        <button type="button" className={btn} disabled={progress !== null} onClick={() => void onDownload()}>
          Download
        </button>
        {progress !== null && (
          <>
            <span role="status" className="text-xs text-muted-foreground">Downloading… {progress.toLocaleString()} lines</span>
            <button type="button" className={btn} onClick={() => abortRef.current?.abort()}>
              Cancel
            </button>
          </>
        )}
        {live && !stream.connected && <span className="text-xs text-muted-foreground">Reconnecting…</span>}
      </div>
      {(stream.logTruncated || overflow) && (
        <p role="status" className="rounded-md border bg-muted p-2 text-sm">
          Showing the latest {MAX_LOG.toLocaleString()} lines. Download the log for the full history.
        </p>
      )}
      <p data-testid="log-count" aria-live="polite" className="sr-only">
        {countText}
      </p>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        role="log"
        aria-live="off"
        aria-label="Log lines"
        tabIndex={0}
        className="h-96 overflow-auto rounded-md border bg-card font-mono text-xs"
      >
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {v.getVirtualItems().map((vi) => {
            const l = rows[vi.index];
            if (!l) return null;
            return (
              <div
                key={l.id}
                data-testid="log-row"
                className="absolute left-0 flex w-full gap-2 whitespace-pre px-2"
                style={{ height: ROW_H, lineHeight: `${ROW_H}px`, transform: `translateY(${vi.start}px)` }}
              >
                <span className="text-muted-foreground">{l.ts.slice(11, 19)}</span>
                <span className={`w-12 shrink-0 uppercase ${LEVEL_CLASS[l.level] ?? ""}`}>{l.level}</span>
                <span className="min-w-0 truncate">{highlight(l.msg, query)}</span>
              </div>
            );
          })}
        </div>
      </div>
      {rows.length === 0 && !first.isPending && <p className="text-sm text-muted-foreground">No log lines match.</p>}
    </section>
  );
}
