import { useInfiniteQuery, type InfiniteData, type UseInfiniteQueryResult } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys, type Resource } from "../../api/keys";
import type { paths } from "../../api/schema";

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}

/** Paths whose GET 200 response is a cursor Page. */
export type ListPath = {
  [P in keyof paths]: paths[P] extends {
    get: { responses: { 200: { content: { "application/json": { items: unknown[] } } } } };
  }
    ? P
    : never;
}[keyof paths];

type Ok<P extends ListPath> = paths[P] extends { get: { responses: { 200: { content: { "application/json": infer B } } } } }
  ? B
  : never;
export type ListItem<P extends ListPath> = Ok<P> extends { items: (infer I)[] } ? I : never;
export type ListQuery<P extends ListPath> = paths[P] extends { get: { parameters: { query?: infer Q } } }
  ? Omit<NonNullable<Q>, "cursor" | "limit">
  : never;

export const PAGE_LIMIT = 100;

/** Cursor-paginated list keyed on keys.list(resource, params) (the key SSE patches). */
export function useCursorList<P extends ListPath>(
  resource: Resource,
  path: P,
  params: ListQuery<P> = {} as ListQuery<P>,
  opts: { enabled?: boolean } = {},
): UseInfiniteQueryResult<InfiniteData<Page<ListItem<P>>, string | null>> {
  return useInfiniteQuery({
    queryKey: keys.list(resource, params),
    initialPageParam: null as string | null,
    enabled: opts.enabled ?? true,
    queryFn: async ({ pageParam }) => {
      const query = { ...params, limit: PAGE_LIMIT, ...(pageParam ? { cursor: pageParam } : {}) };
      // The single cast: openapi-fetch cannot resolve a generic path; P is constrained to Page-returning GETs.
      const get = api.GET as unknown as (
        p: string,
        init: { params: { query: object } },
      ) => Promise<{ data?: Page<ListItem<P>>; error?: unknown; response: Response }>;
      return unwrap(await get(path, { params: { query } }));
    },
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
}

export function flatItems<T>(q: { data?: InfiniteData<Page<T>, unknown> }): T[] {
  return q.data?.pages.flatMap((p) => p.items) ?? [];
}
