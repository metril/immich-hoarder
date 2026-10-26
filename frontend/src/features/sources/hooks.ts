import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import type { components } from "../../api/schema";

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
