import { useInfiniteQuery, type InfiniteData, type UseInfiniteQueryResult } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys, type Resource } from "../../api/keys";

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}

export const PAGE_LIMIT = 100;

/** Cursor-paginated list keyed on keys.list(resource, params) (the key SSE patches). */
export function useCursorList<T>(
  resource: Resource,
  params: Record<string, unknown> = {},
  opts: { enabled?: boolean; path?: string } = {},
): UseInfiniteQueryResult<InfiniteData<Page<T>, string | null>> {
  const path = opts.path ?? `/api/v1/${resource}`;
  return useInfiniteQuery({
    queryKey: keys.list(resource, params),
    initialPageParam: null as string | null,
    enabled: opts.enabled ?? true,
    queryFn: async ({ pageParam }) => {
      const query = { ...params, limit: PAGE_LIMIT, ...(pageParam ? { cursor: pageParam } : {}) };
      // Path is dynamic per resource; the response shape is the shared Page envelope.
      const r = await (api.GET as (p: string, init: unknown) => Promise<{ data?: Page<T>; error?: unknown; response: Response }>)(
        path,
        { params: { query } },
      );
      return unwrap(r);
    },
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
}

export function flatItems<T>(q: { data?: InfiniteData<Page<T>, unknown> }): T[] {
  return q.data?.pages.flatMap((p) => p.items) ?? [];
}
