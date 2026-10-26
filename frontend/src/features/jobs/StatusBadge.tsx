import type { components } from "../../api/schema";

const TONE: Record<components["schemas"]["JobStatus"], string> = {
  queued: "bg-muted text-muted-foreground",
  running: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  succeeded: "bg-green-500/15 text-green-700 dark:text-green-300",
  failed: "bg-red-500/15 text-red-700 dark:text-red-300",
  cancelled: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
};

export function StatusBadge({ status }: { status: components["schemas"]["JobStatus"] }) {
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TONE[status]}`}>{status}</span>;
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const tone = outcome === "failed" ? TONE.failed : outcome === "uploaded" || outcome === "linked" ? TONE.succeeded : outcome === "filtered" ? TONE.cancelled : TONE.queued;
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{outcome}</span>;
}
