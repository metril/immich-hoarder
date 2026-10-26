import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import type { components } from "../../api/schema";
import { flatItems, PAGE_LIMIT, useCursorList, type Page } from "../../components/common/useCursorList";

export type JobOut = components["schemas"]["JobOut"];
export type ItemOut = components["schemas"]["ItemOut"];
export type JobStatus = components["schemas"]["JobStatus"];

export const TERMINAL: JobStatus[] = ["succeeded", "failed", "cancelled"];
export const isTerminal = (s: JobStatus) => TERMINAL.includes(s);
export const OUTCOMES = ["uploaded", "linked", "filtered", "failed", "deleted_in_immich", "discovered", "downloaded"] as const;
export const COUNTER_KEYS = ["discovered", "downloaded", "uploaded", "linked", "filtered", "failed", "deleted_in_immich"] as const;

export function count(counters: Record<string, unknown> | undefined, k: string): number {
  const v = counters?.[k];
  return typeof v === "number" ? v : 0;
}

export function useJobs(params: { status?: JobStatus; source_id?: number }) {
  const q = useCursorList("jobs", "/api/v1/jobs", params);
  return { ...q, rows: flatItems(q) };
}

/** Running + queued jobs merged by id (a job moving queued -> running can briefly sit in both lists). Shares cache with the dashboard. */
export function useActiveJobs() {
  const r = useJobs({ status: "running" });
  const q = useJobs({ status: "queued" });
  const byId = new Map<number, JobOut>();
  for (const j of [...q.rows, ...r.rows]) byId.set(j.id, j);
  const active = [...byId.values()];
  return {
    running: active.filter((j) => j.status === "running"),
    queued: active.filter((j) => j.status === "queued"),
    isPending: r.isPending || q.isPending,
    isError: r.isError || q.isError,
    hasMore: !!r.hasNextPage || !!q.hasNextPage,
    refetchFailed: () => [r, q].forEach((x) => x.isError && void x.refetch()),
  };
}

export function useJob(id: number) {
  return useQuery({
    queryKey: keys.detail("jobs", id),
    queryFn: async () => unwrap(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })),
  });
}

export function useJobItems(jobId: number, outcome?: string) {
  const q = useInfiniteQuery({
    queryKey: keys.jobItems(jobId, outcome),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }): Promise<Page<ItemOut>> =>
      unwrap(
        await api.GET("/api/v1/jobs/{job_id}/items", {
          params: { path: { job_id: jobId }, query: { limit: PAGE_LIMIT, ...(outcome ? { outcome } : {}), ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  return { ...q, rows: flatItems(q) };
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST("/api/v1/jobs/{job_id}/cancel", { params: { path: { job_id: id } } })),
    onSettled: (_d, _e, id) => {
      void qc.invalidateQueries({ queryKey: keys.detail("jobs", id) });
      void qc.invalidateQueries({ queryKey: ["list", "jobs"] });
    },
  });
}

export function useRetryJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST("/api/v1/jobs/{job_id}/retry", { params: { path: { job_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["list", "jobs"] }),
  });
}

export function thumbUrl(targetId: number, assetId: string): string {
  return `/api/v1/targets/${targetId}/assets/${encodeURIComponent(assetId)}/thumbnail`;
}

export function formatBytes(n: number): string {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${u[i]}`;
}

export function formatDuration(startIso: string | null, endIso: string | null, now = Date.now()): string {
  if (!startIso) return "—";
  const s = Math.max(0, Math.round(((endIso ? new Date(endIso).getTime() : now) - new Date(startIso).getTime()) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : m ? `${m}m ${s % 60}s` : `${s}s`;
}
