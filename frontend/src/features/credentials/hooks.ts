import { useMutation, useQueryClient, type InfiniteData, type QueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import type { components } from "../../api/schema";
import { flatItems, useCursorList, type Page } from "../../components/common/useCursorList";

export type CredentialOut = components["schemas"]["CredentialOut"];
export type CredentialIn = components["schemas"]["CredentialIn"];
export type CredentialPatch = components["schemas"]["CredentialPatch"];
export type CredentialKind = components["schemas"]["CredentialKind"];

const LISTS = ["list", "credentials"] as const;
const invalidate = (qc: QueryClient) => qc.invalidateQueries({ queryKey: LISTS });

export function useCredentials() {
  const q = useCursorList("credentials", "/api/v1/credentials");
  return { ...q, rows: flatItems(q) };
}

export function useCreateCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CredentialIn) => unwrap(await api.POST("/api/v1/credentials", { body })),
    onSuccess: () => invalidate(qc),
  });
}

export function useUpdateCredential(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CredentialPatch) =>
      unwrap(await api.PATCH("/api/v1/credentials/{obj_id}", { params: { path: { obj_id: id } }, body })),
    onSuccess: () => invalidate(qc),
  });
}

export function useDeleteCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.DELETE("/api/v1/credentials/{obj_id}", { params: { path: { obj_id: id } } })),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: LISTS });
      const prev = qc.getQueriesData<InfiniteData<Page<CredentialOut>>>({ queryKey: LISTS });
      qc.setQueriesData<InfiniteData<Page<CredentialOut>>>({ queryKey: LISTS }, (d) =>
        d && { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.filter((c) => c.id !== id) })) },
      );
      return { prev };
    },
    onError: (_e, _id, ctx) => ctx?.prev.forEach(([k, v]) => qc.setQueryData(k, v)),
    onSettled: () => invalidate(qc),
  });
}
