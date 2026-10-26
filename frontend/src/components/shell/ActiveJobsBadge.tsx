import { useActiveJobs } from "../../features/jobs/hooks";
import { Badge } from "../ui/badge";

/** Live count of running + queued jobs; fed by the dashboard SSE stream's cache patches (no polling). */
export function ActiveJobsBadge({ className }: { className?: string }) {
  const { running, queued, isPending, isError, hasMore } = useActiveJobs();
  const total = running.length + queued.length;
  if (isPending || isError || total === 0) return null;
  const n = `${total}${hasMore ? "+" : ""}`;
  return (
    <Badge
      tone="info"
      title={`${running.length} running, ${queued.length} queued`}
      className={className}
    >
      {running.length > 0 ? (
        <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-info motion-safe:animate-pulse" />
      ) : null}
      <span aria-hidden>{n}</span>
      <span className="sr-only">, {n} active {total === 1 && !hasMore ? "job" : "jobs"}</span>
    </Badge>
  );
}
