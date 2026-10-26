import { Link } from "@tanstack/react-router";
import { EmptyState } from "../../components/common/EmptyState";
import { count, COUNTER_KEYS, type JobOut } from "../jobs/hooks";
import { JobProgress } from "../jobs/JobProgress";
import { StatusBadge } from "../jobs/StatusBadge";

export function LiveJobs({ jobs, hasSources }: { jobs: JobOut[]; hasSources: boolean }) {
  if (!jobs.length)
    return (
      <EmptyState
        title="No jobs running"
        action={
          hasSources ? (
            <Link to="/sources" className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
              Run a source
            </Link>
          ) : undefined
        }
      />
    );
  return (
    <ul className="grid gap-3">
      {jobs.map((j) => (
        <li key={j.id} className="grid gap-2 rounded-lg border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/jobs/$jobId" params={{ jobId: String(j.id) }} className="font-medium underline focus-visible:outline-2 focus-visible:outline-ring">
              #{j.id}
            </Link>
            <span className="text-sm">{j.source_name ?? ""}</span>
            <StatusBadge status={j.status} />
            {j.phase && <span className="text-xs text-muted-foreground">{j.phase}</span>}
          </div>
          <JobProgress job={j} />
          <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
            {COUNTER_KEYS.filter((k) => count(j.counters, k) > 0).map((k) => (
              <span key={k}>
                {k.replaceAll("_", " ")} <b className="tabular-nums text-foreground">{count(j.counters, k)}</b>
              </span>
            ))}
          </p>
        </li>
      ))}
    </ul>
  );
}
