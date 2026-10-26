import { useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { Dialog } from "radix-ui";
import { isAdmin, useMe } from "../../api/me";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { SharingDialog } from "../../components/common/SharingDialog";
import { useMediaQuery } from "../../components/common/useMediaQuery";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";
import { VisibilityBadge } from "../../components/common/VisibilityBadge";
import { AlbumsList } from "./AlbumsList";
import { TargetForm } from "./TargetForm";
import { TargetTestButton } from "./TargetTestButton";
import { useDeleteTarget, useTargets, type TargetOut } from "./hooks";

const route = getRouteApi("/_app/targets");
const btn = "rounded-md border px-2 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring";

function AlbumsSheet({ t }: { t: TargetOut }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className={btn} aria-label={`Albums of ${t.name}`}>
        Albums
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full max-w-sm overflow-auto border-l bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">Albums · {t.name}</Dialog.Title>
          <Dialog.Description className="sr-only">Albums on this Immich server</Dialog.Description>
          <div className="mt-3">
            <AlbumsList targetId={t.id} enabled={open} />
          </div>
          <Dialog.Close className={`${btn} mt-4`}>Close</Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Actions({ t }: { t: TargetOut }) {
  const del = useDeleteTarget();
  const me = useMe().data;
  const owns = me != null && (me.id === t.owner_id || isAdmin(me));
  return (
    <div className="flex flex-wrap gap-1">
      <TargetTestButton id={t.id} name={t.name} />
      <AlbumsSheet t={t} />
      {owns && <SharingDialog resource="targets" id={t.id} ownerId={t.owner_id} />}
      {t.can_edit && (
        <TargetForm target={t} trigger={<button type="button" aria-label={`Edit ${t.name}`} className={btn}>Edit</button>} />
      )}
      {owns && (
      <ConfirmDialog
        title={`Delete ${t.name}?`}
        body="Jobs using this target will stop working."
        confirmLabel="Delete"
        destructive
        onConfirm={() => del.mutateAsync(t.id).then(() => undefined)}
        trigger={<button type="button" aria-label={`Delete ${t.name}`} className={btn}>Delete</button>}
      />
      )}
    </div>
  );
}

const columns: Column<TargetOut>[] = [
  { id: "name", header: "Name", cell: (t) => <span className="block truncate" title={t.name}>{t.name}</span>, width: "minmax(0,1fr)" },
  { id: "url", header: "URL", cell: (t) => <span className="block truncate" title={t.url}>{t.url}</span>, width: "minmax(0,1.2fr)" },
  { id: "vis", header: "Visibility", cell: (t) => <VisibilityBadge visibility={t.visibility} />, width: "8rem" },
  {
    id: "key",
    header: "API key",
    cell: (t) => (t.has_api_key ? <span className="rounded-full border px-2 py-0.5 text-xs">API key saved</span> : "—"),
    width: "9rem",
  },
  { id: "actions", header: "Actions", cell: (t) => <Actions t={t} />, width: "22rem" },
];

export default function TargetsPage() {
  const q = useTargets();
  const mobile = useMediaQuery("(max-width: 767px)");
  const search = route.useSearch();
  const navigate = useNavigate();
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Targets</h1>
        <TargetForm
          open={search.new === true}
          onOpenChange={(o) => void navigate({ to: "/targets", search: o ? { new: true } : {}, replace: !o })}
          trigger={<button type="button" className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring">Add target</button>} />
      </div>
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : (
        <VirtualTable
          label="Targets"
          rows={q.rows}
          columns={columns}
          rowHeight={mobile ? 260 : 56}
          getRowId={(t) => t.id}
          onEndReached={() => {
            if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
          }}
          empty={<EmptyState title="No targets yet" hint="Add an Immich server to upload to." />}
        />
      )}
    </div>
  );
}
