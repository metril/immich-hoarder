import { useEffect } from "react";
import { useQueryClient, type InfiniteData, type QueryClient } from "@tanstack/react-query";
import { keys } from "../api/keys";
import type { components } from "../api/schema";
import { openStream } from "./sse";
import type { JobEvent } from "./types";

type JobOut = components["schemas"]["JobOut"];
type Pages = InfiniteData<{ items: JobOut[] }>;

function patchJob(j: JobOut, ev: JobEvent): JobOut {
  if (ev.type === "progress") return { ...j, counters: { ...j.counters, ...ev.counters } };
  if (ev.type === "status") return { ...j, status: ev.status };
  if (ev.type === "phase") return { ...j, phase: ev.name };
  return j;
}

function knownInList(qc: QueryClient, id: number): boolean {
  return qc
    .getQueriesData<Pages>({ queryKey: ["list", "jobs"] })
    .some(([, d]) => d?.pages?.some((p) => p.items.some((j) => j.id === id)));
}

function apply(qc: QueryClient, ev: JobEvent) {
  if (ev.type === "gap") {
    void qc.invalidateQueries({ queryKey: keys.list("jobs").slice(0, 2) });
    return;
  }
  if (ev.type !== "progress" && ev.type !== "status" && ev.type !== "phase") return;
  const id = ev.job_id;
  if (typeof id !== "number") return;
  if (ev.type === "status") {
    const terminal = ev.status !== "running" && ev.status !== "queued";
    if (terminal || !knownInList(qc, id)) void qc.invalidateQueries({ queryKey: ["list", "jobs"] });
    if (terminal) void qc.invalidateQueries({ queryKey: ["uploads"] });
  }
  qc.setQueryData<JobOut>(keys.detail("jobs", id), (old) => (old ? patchJob(old, ev) : old));
  qc.setQueriesData<Pages>({ queryKey: ["list", "jobs"] }, (old) => {
    if (!old?.pages) return old;
    let hit = false;
    const pages = old.pages.map((p) => {
      if (!p.items.some((j) => j.id === id)) return p;
      hit = true;
      return { ...p, items: p.items.map((j) => (j.id === id ? patchJob(j, ev) : j)) };
    });
    return hit ? { ...old, pages } : old;
  });
}

/** Mount once in the authenticated layout: keeps job caches live from the dashboard stream. */
export function useDashboardStream() {
  const qc = useQueryClient();
  useEffect(() => openStream("/api/v1/jobs/stream", (ev) => apply(qc, ev)), [qc]);
}
