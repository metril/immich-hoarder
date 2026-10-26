import { useState } from "react";
import { Link, getRouteApi } from "@tanstack/react-router";
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

  if (job.isPending) return <p role="status">Loading job…</p>;
  if (job.isError) return <p role="alert" className="text-destructive">{job.error.message}</p>;
  const j = job.data;

  return (
    <div className="grid gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Job #{j.id}</h1>
        <StatusBadge status={j.status} />
        <Link to="/jobs" search={{ source_id: j.source_id }} className="text-sm underline">
          {j.source_name ?? `Source ${j.source_id}`}
        </Link>
        {j.phase && <span className="text-sm text-muted-foreground">Phase: {j.phase}</span>}
        <span className="text-sm text-muted-foreground">
          Started <RelativeTime iso={j.started_at} /> · {formatDuration(j.started_at, j.finished_at)}
        </span>
        {!stream.connected && j.status === "running" && <span className="text-xs text-muted-foreground">Reconnecting…</span>}
      </header>
      {j.error && <p role="alert" className="rounded-md border border-destructive p-2 text-sm text-destructive">{j.error}</p>}
      <JobActions job={j} />
      <JobProgress job={j} total={stream.total} />
      <JobCounters job={j} rate={stream.rate} scratchBytes={stream.scratchBytes} />
      <div
        role="tablist"
        aria-label="Job details"
        className="flex gap-2"
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
            className={`h-9 rounded-md border px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring ${tab === t ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}
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
  );
}
