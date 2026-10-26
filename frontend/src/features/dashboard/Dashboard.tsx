import { useMe } from "../../api/me";
import { useJobs } from "../jobs/hooks";
import { useSources } from "../sources/hooks";
import { LiveJobs } from "./LiveJobs";
import { RecentUploads } from "./RecentUploads";
import { failedLast24h } from "./hooks";
import { StatTiles } from "./StatTiles";

export default function Dashboard() {
  const me = useMe().data;
  const running = useJobs({ status: "running" });
  const queued = useJobs({ status: "queued" });
  const failed = useJobs({ status: "failed" });
  const sources = useSources();
  const live = [...running.rows, ...queued.rows];
  return (
    <div className="grid gap-6 p-4">
      <h1 className="text-xl font-semibold">{me?.name ? `Welcome, ${me.name}` : "Dashboard"}</h1>
      <StatTiles running={running.rows.length} queued={queued.rows.length} failed={failedLast24h(failed.rows)} sources={sources.rows.length} />
      <section aria-labelledby="live-h" className="grid gap-2">
        <h2 id="live-h" className="text-base font-semibold">Live jobs</h2>
        <LiveJobs jobs={live} hasSources={sources.rows.length > 0} />
      </section>
      <section aria-labelledby="up-h" className="grid gap-2">
        <h2 id="up-h" className="text-base font-semibold">Recent uploads</h2>
        <RecentUploads />
      </section>
    </div>
  );
}
