import { useMutation, useQuery, useQueryClient, type InfiniteData, type QueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import type { components } from "../../api/schema";
import { flatItems, useCursorList, type Page } from "../../components/common/useCursorList";

export type TargetOut = components["schemas"]["TargetOut"];
export type TargetIn = components["schemas"]["TargetIn"];
export type TargetPatch = components["schemas"]["TargetPatch"];

const LISTS = ["list", "targets"] as const;
const invalidate = (qc: QueryClient) => qc.invalidateQueries({ queryKey: LISTS });

export function useTargets() {
  const q = useCursorList("targets", "/api/v1/targets");
  return { ...q, rows: flatItems(q) };
}

export function useCreateTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: TargetIn) => unwrap(await api.POST("/api/v1/targets", { body })),
    onSuccess: () => invalidate(qc),
  });
}

export function useUpdateTarget(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: TargetPatch) =>
      unwrap(await api.PATCH("/api/v1/targets/{obj_id}", { params: { path: { obj_id: id } }, body })),
    onSuccess: () => invalidate(qc),
  });
}

export function useDeleteTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.DELETE("/api/v1/targets/{obj_id}", { params: { path: { obj_id: id } } })),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: LISTS });
      const prev = qc.getQueriesData<InfiniteData<Page<TargetOut>>>({ queryKey: LISTS });
      qc.setQueriesData<InfiniteData<Page<TargetOut>>>({ queryKey: LISTS }, (d) =>
        d && { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.filter((t) => t.id !== id) })) },
      );
      return { prev };
    },
    onError: (_e, _id, ctx) => ctx?.prev.forEach(([k, v]) => qc.setQueryData(k, v)),
    onSettled: () => invalidate(qc),
  });
}

export function useTestTarget() {
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.POST("/api/v1/targets/{obj_id}/test", { params: { path: { obj_id: id } } })),
  });
}

export function useAlbums(id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.albums(id),
    enabled,
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/targets/{obj_id}/albums", { params: { path: { obj_id: id } } })),
  });
}
