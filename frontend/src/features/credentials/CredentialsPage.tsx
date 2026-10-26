import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { SharingDialog } from "../../components/common/SharingDialog";
import { useMediaQuery } from "../../components/common/useMediaQuery";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";
import { VisibilityBadge } from "../../components/common/VisibilityBadge";
import { CredentialForm } from "./CredentialForm";
import { useCredentials, useDeleteCredential, type CredentialOut } from "./hooks";

const btn = "rounded-md border px-2 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring";

function Actions({ c }: { c: CredentialOut }) {
  const del = useDeleteCredential();
  return (
    <div className="flex flex-wrap gap-1">
      <SharingDialog resource="credentials" id={c.id} ownerId={c.owner_id} />
      <CredentialForm credential={c} trigger={<button type="button" aria-label={`Edit ${c.name}`} className={btn}>Edit</button>} />
      <ConfirmDialog
        title={`Delete ${c.name}?`}
        body="Sources and notifications using this credential will lose access."
        confirmLabel="Delete"
        destructive
        onConfirm={() => del.mutateAsync(c.id).then(() => undefined)}
        trigger={<button type="button" aria-label={`Delete ${c.name}`} className={btn}>Delete</button>}
      />
    </div>
  );
}

const columns: Column<CredentialOut>[] = [
  { id: "name", header: "Name", cell: (c) => c.name },
  { id: "site", header: "Site", cell: (c) => c.site },
  { id: "kind", header: "Kind", cell: (c) => c.kind, width: "7rem" },
  { id: "vis", header: "Visibility", cell: (c) => <VisibilityBadge visibility={c.visibility} />, width: "8rem" },
  { id: "secret", header: "Secret", cell: (c) => (c.has_secret ? "Secret saved" : "No secret"), width: "8rem" },
  { id: "actions", header: "Actions", cell: (c) => <Actions c={c} />, width: "14rem" },
];

export default function CredentialsPage() {
  const q = useCredentials();
  const mobile = useMediaQuery("(max-width: 767px)");
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Credentials</h1>
        <CredentialForm trigger={<button type="button" className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring">Add credential</button>} />
      </div>
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : (
        <VirtualTable
          label="Credentials"
          rows={q.rows}
          columns={columns}
          rowHeight={mobile ? 240 : 56}
          getRowId={(c) => c.id}
          onEndReached={() => {
            if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
          }}
          empty={<EmptyState title="No credentials yet" hint="Add site logins, cookies or notification URLs." />}
        />
      )}
    </div>
  );
}
