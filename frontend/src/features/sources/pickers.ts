import { useEffect } from "react";
import { useCredentials } from "../credentials/hooks";
import { useTargets } from "../targets/hooks";

type Paged = { hasNextPage: boolean; isFetchingNextPage: boolean; isFetchNextPageError: boolean; fetchNextPage: () => unknown };

/** Keep fetching until every page is loaded, so pickers never silently truncate. */
function useDrain(q: Paged) {
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = q;
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && !isFetchNextPageError) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage]);
}

/** Targets the caller may use; an already-saved selection stays listed so the edit form keeps it. */
export function useUsableTargets(keep?: number | null) {
  const q = useTargets();
  useDrain(q);
  return q.rows.filter((t) => t.can_use || t.id === keep);
}

export function useUsableCredentials(keep?: number | null, keepIds: number[] = []) {
  const q = useCredentials();
  useDrain(q);
  return q.rows.filter((c) => c.can_use || c.id === keep || keepIds.includes(c.id));
}
