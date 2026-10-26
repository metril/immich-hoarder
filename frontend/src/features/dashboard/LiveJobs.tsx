import { Link } from "@tanstack/react-router";
import { Play } from "lucide-react";
import { EmptyState } from "../../components/common/EmptyState";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Truncate } from "../../components/ui/truncate";
import { count, COUNTER_KEYS, type JobOut } from "../jobs/hooks";
import { JobProgress } from "../jobs/JobProgress";
import { StatusBadge } from "../jobs/StatusBadge";

export function LiveJobs({ jobs, hasSources }: { jobs: JobOut[]; hasSources: boolean }) {
  if (!jobs.length)
    return (
      <EmptyState
        icon={<Play />}
        title="No jobs running"
        action={
          hasSources ? (
            <Button asChild variant="outline" size="sm">
              <Link to="/sources">Run a source</Link>
            </Button>
          ) : undefined
        }
      />
    );
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {jobs.map((j) => (
        <li key={j.id} className="min-w-0">
          <Card className="grid gap-4 p-5 motion-safe:hover:-translate-y-0.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <Link to="/jobs/$jobId" params={{ jobId: String(j.id) }} className="font-display font-semibold underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring">
                #{j.id}
              </Link>
              <Truncate className="min-w-0 flex-1 text-sm">{j.source_name ?? ""}</Truncate>
              <StatusBadge status={j.status} />
              {j.phase && <span className="text-xs text-muted-foreground">{j.phase}</span>}
            </div>
            <JobProgress job={j} />
            <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {COUNTER_KEYS.filter((k) => count(j.counters, k) > 0).map((k) => (
                <span key={k}>
                  {k.replaceAll("_", " ")} <b className="tabular-nums text-foreground">{count(j.counters, k)}</b>
                </span>
              ))}
            </p>
          </Card>
        </li>
      ))}
    </ul>
  );
}
