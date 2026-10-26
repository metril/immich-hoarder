import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { EmptyState } from "../../components/common/EmptyState";
import { RelativeTime } from "../../components/common/RelativeTime";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";
import { Button } from "../../components/ui/button";
import { PageHeader } from "../../components/ui/page";
import { Select } from "../../components/ui/select";
import { useSources } from "../sources/hooks";
import { StatusBadge } from "./StatusBadge";
import { count, formatDuration, useJobs, type JobOut } from "./hooks";
import { JOB_STATUSES, type JobsSearch } from "./search";

const route = getRouteApi("/_app/jobs/");

const num = (k: string) => (j: JobOut) => <span className="tabular-nums">{count(j.counters, k)}</span>;
const columns: Column<JobOut>[] = [
  { id: "id", header: "Job", width: "72px", cell: (j) => `#${j.id}` },
  { id: "status", header: "Status", width: "110px", cell: (j) => <StatusBadge status={j.status} /> },
  { id: "source", header: "Source", cell: (j) => j.source_name ?? `Source ${j.source_id}` },
  { id: "phase", header: "Phase", hideBelow: "md", width: "100px", cell: (j) => j.phase ?? "" },
  { id: "discovered", header: "Discovered", hideBelow: "md", width: "90px", cell: num("discovered") },
  { id: "uploaded", header: "Uploaded", width: "80px", cell: num("uploaded") },
  { id: "linked", header: "Linked", hideBelow: "md", width: "70px", cell: num("linked") },
  { id: "filtered", header: "Filtered", hideBelow: "md", width: "70px", cell: num("filtered") },
  { id: "failed", header: "Failed", width: "70px", cell: num("failed") },
  { id: "started", header: "Started", width: "110px", cell: (j) => <RelativeTime iso={j.started_at} /> },
  { id: "duration", header: "Duration", hideBelow: "md", width: "90px", cell: (j) => formatDuration(j.started_at, j.finished_at) },
];

export default function JobsPage() {
  const search = route.useSearch();
  const navigate = useNavigate();
  const set = (next: JobsSearch) => void navigate({ to: "/jobs", search: next });
  const jobs = useJobs(search);
  const sources = useSources();

  return (
    <div className="space-y-8">
      <PageHeader title="Jobs" description="Every run, newest first." />
      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Status filter" className="flex flex-wrap gap-2">
          {(["all", ...JOB_STATUSES] as const).map((s) => {
            const active = (search.status ?? "all") === s;
            return (
              <Button
                key={s}
                size="sm"
                variant={active ? "primary" : "outline"}
                aria-pressed={active}
                className="rounded-full px-4 capitalize"
                onClick={() => set({ ...search, status: s === "all" ? undefined : s })}
              >
                {s}
              </Button>
            );
          })}
        </div>
        <label htmlFor="jobs-source" className="sr-only">Source</label>
        <Select
          id="jobs-source"
          className="w-full sm:ml-auto sm:w-56"
          value={search.source_id ?? ""}
          onChange={(e) => set({ ...search, source_id: e.target.value ? Number(e.target.value) : undefined })}
        >
          <option value="">All sources</option>
          {sources.rows.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </Select>
      </div>
      {jobs.isError ? (
        <p role="alert" className="text-danger">{jobs.error.message}</p>
      ) : jobs.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">Loading jobs…</p>
      ) : (
        <VirtualTable
          label="Jobs"
          rows={jobs.rows}
          columns={columns}
          getRowId={(j) => j.id}
          onRowClick={(j) => void navigate({ to: "/jobs/$jobId", params: { jobId: String(j.id) } })}
          onEndReached={() => {
            if (jobs.hasNextPage && !jobs.isFetchingNextPage) void jobs.fetchNextPage();
          }}
          empty={<EmptyState title="No jobs" hint="Run a source to see jobs here." />}
        />
      )}
    </div>
  );
}
