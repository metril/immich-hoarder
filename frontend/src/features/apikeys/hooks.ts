import { useMutation, useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import type { components } from "../../api/schema";
import { flatItems, useCursorList, type Page } from "../../components/common/useCursorList";

export type ApiKeyOut = components["schemas"]["ApiKeyOut"];
export type ApiKeyIn = components["schemas"]["ApiKeyIn"];
export type ApiKeyPatch = components["schemas"]["ApiKeyPatch"];

const LISTS = ["list", "api-keys"] as const;

export function useApiKeys() {
  const q = useCursorList("api-keys", "/api/v1/api-keys");
  return { ...q, rows: flatItems(q) };
}

/**
 * The plaintext key is handed to `onKey` and never returned from the mutation
 * (mutation results live in the MutationCache) nor written to the list cache.
 */
export function useCreateApiKey(onKey: (plaintext: string) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ApiKeyIn): Promise<ApiKeyOut> => {
      const { key, ...out } = unwrap(await api.POST("/api/v1/api-keys", { body }));
      onKey(key);
      return out;
    },
    onSuccess: (out) => {
      qc.setQueriesData<InfiniteData<Page<ApiKeyOut>>>({ queryKey: LISTS }, (d) =>
        d && { ...d, pages: d.pages.map((p, i) => (i === 0 ? { ...p, items: [out, ...p.items] } : p)) },
      );
      void qc.invalidateQueries({ queryKey: LISTS });
    },
  });
}

export function useRevokeApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.DELETE("/api/v1/api-keys/{key_id}", { params: { path: { key_id: id } } })),
    onSuccess: (_d, id) => {
      qc.setQueriesData<InfiniteData<Page<ApiKeyOut>>>({ queryKey: LISTS }, (d) =>
        d && { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.filter((k) => k.id !== id) })) },
      );
      void qc.invalidateQueries({ queryKey: LISTS });
    },
  });
}

function replaceInLists(qc: ReturnType<typeof useQueryClient>, id: number, next: ApiKeyOut) {
  qc.setQueriesData<InfiniteData<Page<ApiKeyOut>>>({ queryKey: LISTS }, (d) =>
    d && { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.map((k) => (k.id === id ? next : k)) })) },
  );
  void qc.invalidateQueries({ queryKey: LISTS });
}

export function useUpdateApiKey(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ApiKeyPatch): Promise<ApiKeyOut> =>
      unwrap(await api.PATCH("/api/v1/api-keys/{key_id}", { params: { path: { key_id: id } }, body })),
    onSuccess: (out) => replaceInLists(qc, id, out),
  });
}

/** Like create: the new plaintext key goes to `onKey` only, never into a cache. */
export function useRotateApiKey(onKey: (plaintext: string) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number): Promise<ApiKeyOut> => {
      const { key, ...out } = unwrap(
        await api.POST("/api/v1/api-keys/{key_id}/rotate", { params: { path: { key_id: id } } }),
      );
      onKey(key);
      return out;
    },
    onSuccess: (out, id) => replaceInLists(qc, id, out),
  });
}
