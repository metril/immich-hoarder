import { COUNTER_KEYS, count, formatBytes, type JobOut } from "./hooks";

export function JobCounters({ job, rate, scratchBytes }: { job: JobOut; rate?: number; scratchBytes?: number }) {
  const tiles: [string, string][] = [
    ...COUNTER_KEYS.map((k): [string, string] => [k.replaceAll("_", " "), String(count(job.counters, k))]),
    ["throughput", rate === undefined ? "—" : `${formatBytes(rate)}/s`],
    ["scratch", scratchBytes === undefined ? "—" : formatBytes(scratchBytes)],
  ];
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" aria-label="Job counters">
      {tiles.map(([label, value]) => (
        <div key={label} className="rounded-md border p-3">
          <dt className="text-xs capitalize text-muted-foreground">{label}</dt>
          <dd className="text-lg font-semibold tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
