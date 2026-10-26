import { useMutation, useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import type { components } from "../../api/schema";
import { flatItems, useCursorList, type Page } from "../../components/common/useCursorList";

export type ApiKeyOut = components["schemas"]["ApiKeyOut"];
export type ApiKeyIn = components["schemas"]["ApiKeyIn"];

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
