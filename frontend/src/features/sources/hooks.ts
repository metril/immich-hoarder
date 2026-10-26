import { useMutation, useQuery, useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import type { components } from "../../api/schema";
import { flatItems, useCursorList, type Page } from "../../components/common/useCursorList";

export type SourceOut = components["schemas"]["SourceOut"];
export type SourceIn = components["schemas"]["SourceIn"];
export type SourcePatch = components["schemas"]["SourcePatch"];
export type FilterSpec = SourceIn["filters"];
export type SourceNotify = SourceIn["notify"];
export type BackfillMode = components["schemas"]["BackfillMode"];

const LISTS = ["list", "sources"] as const;

export function useCreateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SourceIn) => unwrap(await api.POST("/api/v1/sources", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: LISTS }),
  });
}

export function useUpdateSource(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SourcePatch) =>
      unwrap(await api.PATCH("/api/v1/sources/{obj_id}", { params: { path: { obj_id: id } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: LISTS }),
  });
}

export function useExtractors() {
  return useQuery({
    queryKey: keys.extractors(),
    staleTime: Infinity,
    queryFn: async () => unwrap(await api.GET("/api/v1/extractors")),
  });
}

export type PreviewItem = components["schemas"]["PreviewItem"];
export type RipIn = components["schemas"]["RipIn"];

export function useSources() {
  const q = useCursorList("sources", "/api/v1/sources");
  return { ...q, rows: flatItems(q) };
}

export function useSource(id: number | undefined, enabled = true) {
  return useQuery({
    queryKey: keys.detail("sources", id ?? 0),
    enabled: enabled && id !== undefined,
    queryFn: async () => unwrap(await api.GET("/api/v1/sources/{obj_id}", { params: { path: { obj_id: id ?? 0 } } })),
  });
}

type Lists = InfiniteData<Page<SourceOut>>;

/** Optimistic enabled toggle: patch every cached list, roll back on error. */
export function useToggleSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, enabled }: { id: number; enabled: boolean }) =>
      unwrap(await api.PATCH("/api/v1/sources/{obj_id}", { params: { path: { obj_id: id } }, body: { enabled } })),
    onMutate: async ({ id, enabled }) => {
      await qc.cancelQueries({ queryKey: LISTS });
      const prev = qc.getQueriesData<Lists>({ queryKey: LISTS });
      qc.setQueriesData<Lists>({ queryKey: LISTS }, (d) =>
        d && { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.map((s) => (s.id === id ? { ...s, enabled } : s)) })) },
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev.forEach(([k, v]) => qc.setQueryData(k, v)),
    onSettled: () => qc.invalidateQueries({ queryKey: LISTS }),
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => unwrap(await api.DELETE("/api/v1/sources/{obj_id}", { params: { path: { obj_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: LISTS }),
  });
}

export function useRunSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, log_level }: { id: number; log_level?: string }) =>
      unwrap(await api.POST("/api/v1/sources/{source_id}/run", { params: { path: { source_id: id } }, body: log_level ? { log_level } : {} })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["list", "jobs"] }),
  });
}

export function useRip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: RipIn) => unwrap(await api.POST("/api/v1/rip", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["list", "jobs"] }),
  });
}

/** Navigation target for a job page. */
export function jobNav(jobId: number) {
  return { to: "/jobs/$jobId", params: { jobId: String(jobId) } } as const;
}

export const RUN_LOG_LEVELS = ["trace", "debug", "info", "warn", "error"] as const;
