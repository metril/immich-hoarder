import { useMe } from "../../api/me";
import { useJobs, type JobOut } from "../jobs/hooks";
import { useSources } from "../sources/hooks";
import { ErrorState } from "./ErrorState";
import { failedLabel } from "./hooks";
import { LiveJobs } from "./LiveJobs";
import { RecentUploads } from "./RecentUploads";
import { PageHeader } from "../../components/ui/page";
import { StatTiles } from "./StatTiles";

export default function Dashboard() {
  const me = useMe().data;
  const running = useJobs({ status: "running" });
  const queued = useJobs({ status: "queued" });
  const failed = useJobs({ status: "failed" });
  const sources = useSources();
  const qs = [running, queued, failed, sources];
  const isError = qs.some((q) => q.isError);
  const isPending = !isError && qs.some((q) => q.isPending);

  // Lists are separate queries; a job moving queued -> running can briefly sit in both, so merge by id and split by status.
  const byId = new Map<number, JobOut>();
  for (const j of [...queued.rows, ...running.rows]) byId.set(j.id, j);
  const active = [...byId.values()];
  const runningRows = active.filter((j) => j.status === "running");
  const queuedRows = active.filter((j) => j.status === "queued");

  return (
    <div className="space-y-8">
      <PageHeader title={me?.name ? `Welcome, ${me.name}` : "Dashboard"} />
      {isError ? (
        <ErrorState what="jobs" onRetry={() => qs.forEach((q) => q.isError && void q.refetch())} />
      ) : (
        <>
          <StatTiles
            running={isPending ? undefined : runningRows.length}
            queued={isPending ? undefined : queuedRows.length}
            failed={isPending ? undefined : failedLabel(failed.rows, !!failed.hasNextPage)}
            sources={isPending ? undefined : sources.rows.length}
          />
          <section aria-labelledby="live-h" className="grid gap-4">
            <h2 id="live-h" className="font-display text-lg font-semibold">Live jobs</h2>
            {isPending ? (
              <div role="status" aria-label="Loading jobs" className="h-28 animate-pulse rounded-xl bg-muted" />
            ) : (
              <LiveJobs jobs={[...runningRows, ...queuedRows]} hasSources={sources.rows.length > 0} />
            )}
          </section>
        </>
      )}
      <section aria-labelledby="up-h" className="grid gap-4">
        <h2 id="up-h" className="font-display text-lg font-semibold">Recent uploads</h2>
        <RecentUploads />
      </section>
    </div>
  );
}
