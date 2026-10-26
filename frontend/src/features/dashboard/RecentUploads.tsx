import { useState } from "react";
import { Dialog } from "radix-ui";
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
      <div role="status" aria-label="Loading uploads" className="grid animate-pulse gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
        {Array.from({ length: 12 }, (_, i) => (
          <div key={i} className="rounded bg-muted" style={{ aspectRatio: 1 }} />
        ))}
      </div>
    );
  if (!q.rows.length) return <EmptyState title="No uploads yet" hint="Uploaded media will appear here." />;
  return (
    <div className="grid gap-3">
      <ul className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
        {q.rows.map((u, i) => {
          const name = fileName(u.url);
          return (
            <li key={u.id}>
              {broken.has(u.id) ? (
                <span role="img" aria-label={name} className="block w-full rounded bg-muted" style={{ aspectRatio: 1 }} />
              ) : (
                <button type="button" onClick={() => setOpen(u)} aria-label={`Preview ${name}`} className="block w-full rounded focus-visible:outline-2 focus-visible:outline-ring">
                  <img
                    src={thumbUrl(u.target_id, u.immich_asset_id!)}
                    alt={name}
                    width={160}
                    height={160}
                    loading={i < EAGER ? undefined : "lazy"}
                    fetchPriority={i < EAGER ? "high" : undefined}
                    decoding="async"
                    onError={() => setBroken((b) => new Set(b).add(u.id))}
                    className="w-full rounded bg-muted object-cover"
                    style={{ aspectRatio: 1 }}
                  />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {q.hasNextPage && (
        <button
          type="button"
          disabled={q.isFetchingNextPage}
          onClick={() => void q.fetchNextPage()}
          className="justify-self-center rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          Load more
        </button>
      )}
      <Dialog.Root open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-popover p-3 text-popover-foreground shadow-xl">
            <Dialog.Title className="truncate text-sm font-semibold">{open ? fileName(open.url) : ""}</Dialog.Title>
            <Dialog.Description className="sr-only">Image preview</Dialog.Description>
            {open && <img src={`${thumbUrl(open.target_id, open.immich_asset_id!)}?size=preview`} alt={fileName(open.url)} className="mx-auto mt-2 max-h-[75vh] object-contain" />}
            <Dialog.Close className="mt-2 rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">Close</Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
