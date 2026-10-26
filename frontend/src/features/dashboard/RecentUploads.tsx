import { useState } from "react";
import { Dialog } from "radix-ui";
import { ImageOff } from "lucide-react";
import { Button } from "../../components/ui/button";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "./ErrorState";
import { thumbUrl } from "../jobs/hooks";
import { fileName, useRecentUploads, type UploadOut } from "./hooks";

const EAGER = 6;

export function RecentUploads() {
  const q = useRecentUploads();
  const [broken, setBroken] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<UploadOut | null>(null);
  if (q.isError) return <ErrorState what="recent uploads" onRetry={() => void q.refetch()} />;
  if (q.isPending)
    return (
      <div role="status" aria-label="Loading uploads" className="grid animate-pulse gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
        {Array.from({ length: 12 }, (_, i) => (
          <div key={i} className="rounded-lg bg-muted" style={{ aspectRatio: 1 }} />
        ))}
      </div>
    );
  if (!q.rows.length) return <EmptyState icon={<ImageOff />} title="No uploads yet" hint="Uploaded media will appear here." />;
  return (
    <div className="grid gap-3">
      <ul className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
        {q.rows.map((u, i) => {
          const name = fileName(u.url);
          return (
            <li key={u.id}>
              {broken.has(u.id) ? (
                <span role="img" aria-label={name} className="block w-full rounded-lg bg-muted" style={{ aspectRatio: 1 }} />
              ) : (
                <button type="button" onClick={() => setOpen(u)} aria-label={`Preview ${name}`} className="block w-full overflow-hidden rounded-lg focus-visible:outline-2 focus-visible:outline-ring">
                  <img
                    src={thumbUrl(u.target_id, u.immich_asset_id!)}
                    alt={name}
                    width={160}
                    height={160}
                    loading={i < EAGER ? undefined : "lazy"}
                    fetchPriority={i < EAGER ? "high" : undefined}
                    decoding="async"
                    onError={() => setBroken((b) => new Set(b).add(u.id))}
                    className="w-full bg-muted object-cover motion-safe:transition-transform motion-safe:duration-150 motion-safe:hover:scale-105"
                    style={{ aspectRatio: 1 }}
                  />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {q.hasNextPage && (
        <Button variant="outline" className="justify-self-center" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
          Load more
        </Button>
      )}
      <Dialog.Root open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-xl border bg-popover p-5 text-popover-foreground shadow-xl">
            <Dialog.Title className="truncate pr-2 font-display text-sm font-semibold" title={open ? fileName(open.url) : undefined}>{open ? fileName(open.url) : ""}</Dialog.Title>
            <Dialog.Description className="sr-only">Image preview</Dialog.Description>
            {open && <img src={`${thumbUrl(open.target_id, open.immich_asset_id!)}?size=preview`} alt={fileName(open.url)} className="mx-auto my-4 max-h-[70vh] object-contain" />}
            <Dialog.Close asChild><Button variant="outline">Close</Button></Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
