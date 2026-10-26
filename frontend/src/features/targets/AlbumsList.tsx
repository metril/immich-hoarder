import { Truncate } from "@/components/ui/truncate";
import { useAlbums } from "./hooks";

export function AlbumsList({ targetId, enabled }: { targetId: number; enabled: boolean }) {
  const q = useAlbums(targetId, enabled);
  if (q.isPending) return <p role="status" className="text-sm text-muted-foreground">Loading albums…</p>;
  if (q.isError) return <p role="alert" className="text-sm text-destructive">{q.error.message}</p>;
  const items = q.data.items;
  if (items.length === 0) return <p className="text-sm text-muted-foreground">No albums.</p>;
  return (
    <ul className="divide-y rounded-lg border">
      {items.map((a) => (
        <li key={a.id} className="flex min-w-0 items-center justify-between gap-3 px-4 py-3 text-sm">
          <Truncate className="min-w-0 flex-1">{a.name}</Truncate>
          <span className="shrink-0 text-muted-foreground">{a.asset_count} assets</span>
        </li>
      ))}
    </ul>
  );
}
