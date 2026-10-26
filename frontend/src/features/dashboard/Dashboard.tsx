import { useMe } from "../../api/me";
import { useActiveJobs, useJobs } from "../jobs/hooks";
import { useSources } from "../sources/hooks";
import { ErrorState } from "./ErrorState";
import { failedLabel } from "./hooks";
import { LiveJobs } from "./LiveJobs";
import { RecentUploads } from "./RecentUploads";
import { PageHeader } from "../../components/ui/page";
import { StatTiles } from "./StatTiles";

export default function Dashboard() {
  const me = useMe().data;
  const active = useActiveJobs();
  const failed = useJobs({ status: "failed" });
  const sources = useSources();
  const qs = [failed, sources];
  const isError = active.isError || qs.some((q) => q.isError);
  const isPending = !isError && (active.isPending || qs.some((q) => q.isPending));
  const runningRows = active.running;
  const queuedRows = active.queued;

  return (
    <div className="space-y-8">
      <PageHeader title={me?.name ? `Welcome, ${me.name}` : "Dashboard"} />
      {isError ? (
        <ErrorState what="jobs" onRetry={() => { active.refetchFailed(); qs.forEach((q) => q.isError && void q.refetch()); }} />
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
