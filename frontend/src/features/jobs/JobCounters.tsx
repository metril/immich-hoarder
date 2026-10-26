import { StatTile } from "../../components/ui/stat-tile";
import { COUNTER_KEYS, count, formatBytes, type JobOut } from "./hooks";

export function JobCounters({ job, rate, scratchBytes }: { job: JobOut; rate?: number; scratchBytes?: number }) {
  const tiles: [string, string][] = [
    ...COUNTER_KEYS.map((k): [string, string] => [k.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase()).replace("immich", "Immich"), String(count(job.counters, k))]),
    ["throughput", rate === undefined ? "—" : `${formatBytes(rate)}/s`],
    ["scratch", scratchBytes === undefined ? "—" : formatBytes(scratchBytes)],
  ];
  return (
    <div role="group" className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5" aria-label="Job counters">
      {tiles.map(([label, value]) => (
        <StatTile key={label} label={label} value={value} className="p-4" />
      ))}
    </div>
  );
}
