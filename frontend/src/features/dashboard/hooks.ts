import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import type { components } from "../../api/schema";
import type { Page } from "../../components/common/useCursorList";

export type UploadOut = components["schemas"]["UploadOut"];
export const UPLOADS_LIMIT = 60;
const params = { limit: UPLOADS_LIMIT };

/** Latest uploads, keyed on keys.uploads so job completion (T5) refetches it. */
export function useRecentUploads() {
  const q = useInfiniteQuery({
    queryKey: keys.uploads(params),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }): Promise<Page<UploadOut>> =>
      unwrap(await api.GET("/api/v1/uploads", { params: { query: { ...params, ...(pageParam ? { cursor: pageParam } : {}) } } })),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  // The uploads API has no server-side filter for rows lacking immich_asset_id (only source_id/target_id),
  // so they are dropped client-side; a page may therefore render fewer than 60 images.
  const rows = (q.data?.pages.flatMap((p) => p.items) ?? []).filter((u) => u.immich_asset_id);
  return { ...q, rows };
}

export function fileName(url: string): string {
  try {
    const last = new URL(url).pathname.split("/").filter(Boolean).at(-1);
    return last ? decodeURIComponent(last) : url;
  } catch {
    return url;
  }
}

const DAY = 24 * 3600 * 1000;

export function failedLast24h(jobs: { finished_at: string | null; created_at: string }[], now = Date.now()): number {
  return jobs.filter((j) => now - new Date(j.finished_at ?? j.created_at).getTime() <= DAY).length;
}

/** Tile label: "N+" when more failed jobs may exist beyond the loaded pages and all loaded rows are recent. */
export function failedLabel(jobs: { finished_at: string | null; created_at: string }[], hasNextPage: boolean, now = Date.now()): string {
  const n = failedLast24h(jobs, now);
  return hasNextPage && n === jobs.length ? `${n}+` : String(n);
}
