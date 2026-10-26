import { count, isTerminal, type JobOut } from "./hooks";

const DONE = ["uploaded", "linked", "filtered", "failed", "deleted_in_immich"] as const;

function eta(job: JobOut, done: number, total: number): string {
  if (!job.started_at || done <= 0 || done >= total) return "";
  const elapsed = (Date.now() - new Date(job.started_at).getTime()) / 1000;
  const left = Math.round((elapsed / done) * (total - done));
  return left >= 60 ? `ETA ~${Math.ceil(left / 60)}m` : `ETA ~${left}s`;
}

export function JobProgress({ job, total }: { job: JobOut; total?: number }) {
  const done = DONE.reduce((n, k) => n + count(job.counters, k), 0);
  const terminal = isTerminal(job.status);
  const determinate = total !== undefined && total > 0;
  const pct = determinate ? Math.min(100, (done / total) * 100) : terminal ? 100 : undefined;
  const text = determinate ? `${done} of ${total} processed` : `${done} processed`;
  return (
    <div className="grid gap-1">
      <div
        role="progressbar"
        aria-label="Job progress"
        aria-valuemin={0}
        aria-valuemax={determinate ? total : undefined}
        aria-valuenow={determinate ? done : undefined}
        aria-valuetext={text}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={`h-full bg-primary ${pct === undefined ? "w-1/3 animate-pulse motion-reduce:animate-none" : ""}`}
          style={pct === undefined ? undefined : { width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        {text} {determinate && !terminal ? eta(job, done, total) : ""}
      </p>
    </div>
  );
}
