import { useMemo, useState } from "react";
import { inputClass } from "../../components/common/FormField";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";
import type { Item } from "../../live/types";
import { OutcomeBadge } from "./StatusBadge";
import { OUTCOMES, thumbUrl, useJobItems, type ItemOut } from "./hooks";

export function ItemsTable({ jobId, hostTargetId, live }: { jobId: number; hostTargetId?: number; live: Item[] }) {
  const [outcome, setOutcome] = useState("");
  const [broken, setBroken] = useState<Set<number>>(new Set());
  const q = useJobItems(jobId, outcome || undefined);
  const rows = useMemo(() => {
    const paged = q.rows;
    const seen = new Set(paged.map((r) => r.id));
    const fresh: ItemOut[] = [];
    for (let i = live.length - 1; i >= 0; i--) {
      const it = live[i];
      if (!it) continue;
      const o = it.type.slice("item.".length);
      if (seen.has(it.id) || (outcome && o !== outcome)) continue;
      seen.add(it.id);
      fresh.push({ id: it.id, url: it.url, outcome: o, reason: it.reason ?? null, immich_asset_id: it.immich_asset_id ?? null });
    }
    return [...fresh, ...paged];
  }, [q.rows, live, outcome]);

  const columns: Column<ItemOut>[] = [
    {
      id: "thumb",
      header: "Thumb",
      width: "64px",
      cell: (r) =>
        r.immich_asset_id && hostTargetId !== undefined && !broken.has(r.id) ? (
          <img
            loading="lazy"
            decoding="async"
            width={48}
            height={48}
            alt=""
            src={thumbUrl(hostTargetId, r.immich_asset_id)}
            onError={() => setBroken((b) => new Set(b).add(r.id))}
            className="h-9 w-9 rounded object-cover"
          />
        ) : (
          <span aria-hidden className="inline-block h-9 w-9 rounded bg-muted" />
        ),
    },
    {
      id: "url",
      header: "URL",
      width: "minmax(0,2fr)",
      cell: (r) => (
        <a href={r.url} target="_blank" rel="noreferrer" title={r.url} className="underline">
          {r.url}
        </a>
      ),
    },
    { id: "outcome", header: "Outcome", width: "140px", cell: (r) => <OutcomeBadge outcome={r.outcome} /> },
    { id: "reason", header: "Reason", hideBelow: "md", cell: (r) => r.reason ?? "" },
  ];

  return (
    <section className="grid gap-2" aria-label="Items">
      <div className="flex items-center gap-2">
        <label htmlFor="items-outcome" className="text-sm font-medium">Outcome</label>
        <select id="items-outcome" className={`${inputClass} w-auto`} value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">All</option>
          {OUTCOMES.map((o) => (
            <option key={o} value={o}>{o.replaceAll("_", " ")}</option>
          ))}
        </select>
      </div>
      <VirtualTable
        label="Items"
        rows={rows}
        columns={columns}
        rowHeight={52}
        getRowId={(r) => r.id}
        onEndReached={() => {
          if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
        }}
        empty={<p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">No items yet.</p>}
      />
    </section>
  );
}
