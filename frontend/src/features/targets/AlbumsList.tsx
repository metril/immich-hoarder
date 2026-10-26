import { useAlbums } from "./hooks";

export function AlbumsList({ targetId, enabled }: { targetId: number; enabled: boolean }) {
  const q = useAlbums(targetId, enabled);
  if (q.isPending) return <p role="status">Loading albums…</p>;
  if (q.isError) return <p role="alert" className="text-destructive">{q.error.message}</p>;
  const items = q.data.items;
  if (items.length === 0) return <p className="text-sm text-muted-foreground">No albums.</p>;
  return (
    <ul className="divide-y rounded-md border">
      {items.map((a) => (
        <li key={a.id} className="flex justify-between gap-2 px-3 py-2 text-sm">
          <span className="min-w-0 truncate">{a.name}</span>
          <span className="text-muted-foreground">{a.asset_count} assets</span>
        </li>
      ))}
    </ul>
  );
}
