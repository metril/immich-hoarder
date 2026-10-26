export function StatTiles({ running, queued, failed, sources }: { running?: number; queued?: number; failed?: string; sources?: number }) {
  const tiles = [
    ["Running", running],
    ["Queued", queued],
    ["Failed (24 h)", failed],
    ["Sources", sources],
  ] as const;
  return (
    <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {tiles.map(([label, n]) => (
        <div key={label} className="rounded-lg border p-3">
          <dt className="text-sm text-muted-foreground">{label}</dt>
          <dd className="text-2xl font-semibold tabular-nums">
            {n === undefined ? <span role="status" aria-label={`Loading ${label}`} className="inline-block h-8 w-10 animate-pulse rounded bg-muted" /> : n}
          </dd>
        </div>
      ))}
    </dl>
  );
}
