import { useState } from "react";
import { Link, getRouteApi } from "@tanstack/react-router";
import { Card } from "../../components/ui/card";
import { Truncate } from "../../components/ui/truncate";
import { cn } from "../../components/ui/cn";
import { RelativeTime } from "../../components/common/RelativeTime";
import { useJobStream } from "../../live/useJobStream";
import { useSource } from "../sources/hooks";
import { ItemsTable } from "./ItemsTable";
import { JobActions } from "./JobActions";
import { JobCounters } from "./JobCounters";
import { LogViewer } from "./LogViewer";
import { JobProgress } from "./JobProgress";
import { StatusBadge } from "./StatusBadge";
import { formatDuration, useJob } from "./hooks";

const route = getRouteApi("/_app/jobs/$jobId");

export default function JobDetail() {
  const id = Number(route.useParams().jobId);
  const job = useJob(id);
  const stream = useJobStream(id);
  const [tab, setTab] = useState<"items" | "log">("items");
  const source = useSource(job.data?.source_id, job.data !== undefined);

  if (job.isPending) return <p role="status" className="text-sm text-muted-foreground">Loading job…</p>;
  if (job.isError) return <p role="alert" className="text-danger">{job.error.message}</p>;
  const j = job.data;

  return (
    <div className="space-y-8">
      <Card className="grid gap-5 p-5 md:p-6">
        <header className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className="font-display text-2xl font-semibold tracking-tight">Job #{j.id}</h1>
          <StatusBadge status={j.status} />
          <Link to="/jobs" search={{ source_id: j.source_id }} className="min-w-0 max-w-full text-sm underline-offset-4 hover:underline">
            <Truncate>{j.source_name ?? `Source ${j.source_id}`}</Truncate>
          </Link>
          {j.phase && <span className="text-sm text-muted-foreground">Phase: {j.phase}</span>}
          <span className="text-sm text-muted-foreground">
            Started <RelativeTime iso={j.started_at} /> · {formatDuration(j.started_at, j.finished_at)}
          </span>
          {!stream.connected && j.status === "running" && <span className="text-xs text-muted-foreground">Reconnecting…</span>}
        </header>
        {j.error && <p role="alert" className="break-words rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{j.error}</p>}
        <JobProgress job={j} total={stream.total} />
        <JobActions job={j} />
      </Card>
      <JobCounters job={j} rate={stream.rate} scratchBytes={stream.scratchBytes} />
      <div className="space-y-4">
        <div
          role="tablist"
          aria-label="Job details"
          className="flex gap-1 border-b"
          onKeyDown={(e) => {
            if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
            const next = tab === "items" ? "log" : "items";
            setTab(next);
            document.getElementById(`tab-${next}`)?.focus();
          }}
        >
          {(["items", "log"] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              id={`tab-${t}`}
              aria-selected={tab === t}
              aria-controls={`panel-${t}`}
              tabIndex={tab === t ? 0 : -1}
              onClick={() => setTab(t)}
              className={cn(
                "-mb-px h-10 border-b-2 px-4 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t === "items" ? "Items" : "Log"}
            </button>
          ))}
        </div>
        <div role="tabpanel" id="panel-items" aria-labelledby="tab-items" hidden={tab !== "items"}>
          <ItemsTable jobId={id} hostTargetId={source.data?.target_id} live={stream.items} />
        </div>
        <div role="tabpanel" id="panel-log" aria-labelledby="tab-log" hidden={tab !== "log"}>
          {tab === "log" && <LogViewer jobId={id} live={j.status === "running"} stream={stream} />}
        </div>
      </div>
    </div>
  );
}
