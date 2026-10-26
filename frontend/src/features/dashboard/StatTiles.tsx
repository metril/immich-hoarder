import { Link } from "@tanstack/react-router";
import { Activity, AlertTriangle, Clock, Database } from "lucide-react";
import type { ReactNode } from "react";
import { StatTile } from "../../components/ui/stat-tile";

type Tone = "info" | "warning" | "danger" | "primary";
type Status = "running" | "queued" | "failed";

export function StatTiles({ running, queued, failed, sources }: { running?: number; queued?: number; failed?: string; sources?: number }) {
  const tiles: { label: string; value: number | string | undefined; icon: ReactNode; tone: Tone; status?: Status }[] = [
    { label: "Running", value: running, icon: <Activity />, tone: "info", status: "running" },
    { label: "Queued", value: queued, icon: <Clock />, tone: "warning", status: "queued" },
    { label: "Failed (24 h)", value: failed, icon: <AlertTriangle />, tone: "danger", status: "failed" },
    { label: "Sources", value: sources, icon: <Database />, tone: "primary" },
  ];
  const cls =
    "block min-w-0 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-safe:transition-transform motion-safe:hover:-translate-y-0.5";
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {tiles.map(({ label, value, icon, tone, status }) => {
        const tile = (
          <StatTile
            label={label}
            icon={icon}
            tone={tone}
            className="h-full"
            value={
              value === undefined ? (
                <span role="status" aria-label={`Loading ${label}`} className="inline-block h-6 w-10 animate-pulse rounded bg-muted" />
              ) : (
                value
              )
            }
          />
        );
        return status ? (
          <Link key={label} to="/jobs" search={{ status }} className={cls}>
            {tile}
          </Link>
        ) : (
          <Link key={label} to="/sources" className={cls}>
            {tile}
          </Link>
        );
      })}
    </div>
  );
}
