import { Link, getRouteApi } from "@tanstack/react-router";
import { RelativeTime } from "../../components/common/RelativeTime";
import { useJobStream } from "../../live/useJobStream";
import { useSource } from "../sources/hooks";
import { ItemsTable } from "./ItemsTable";
import { JobActions } from "./JobActions";
import { JobCounters } from "./JobCounters";
import { JobProgress } from "./JobProgress";
import { StatusBadge } from "./StatusBadge";
import { formatDuration, useJob } from "./hooks";

const route = getRouteApi("/_app/jobs/$jobId");

export default function JobDetail() {
  const id = Number(route.useParams().jobId);
  const job = useJob(id);
  const stream = useJobStream(id);
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
      {/* T12: log viewer mounts here (tab "Log") using the same useJobStream(id) state. */}
      <ItemsTable jobId={id} hostTargetId={source.data?.target_id} live={stream.items} />
    </div>
  );
}
