import { useState } from "react";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { formatRelative } from "../../components/common/formatRelative";
import { useMediaQuery } from "../../components/common/useMediaQuery";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";
import { ApiKeyForm } from "./ApiKeyForm";
import { useApiKeys, useRevokeApiKey, type ApiKeyOut } from "./hooks";
import { KeyRevealDialog } from "./KeyRevealDialog";

function Revoke({ k }: { k: ApiKeyOut }) {
  const revoke = useRevokeApiKey();
  return (
    <ConfirmDialog
      title={`Revoke ${k.name}?`}
      body="Anything using this key will stop working immediately."
      confirmLabel="Revoke"
      destructive
      onConfirm={() => revoke.mutateAsync(k.id).then(() => undefined)}
      trigger={
        <button type="button" aria-label={`Revoke ${k.name}`} className="rounded-md border px-2 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
          Revoke
        </button>
      }
    />
  );
}

const isPast = (iso: string) => new Date(iso).getTime() < Date.now();

function Expires({ iso }: { iso: string | null }) {
  if (!iso) return <span>Never</span>;
  const past = isPast(iso);
  return (
    <time dateTime={iso} title={new Date(iso).toLocaleString()} className={past ? "font-medium text-destructive" : undefined}>
      {past ? `Expired ${formatRelative(iso)}` : formatRelative(iso)}
    </time>
  );
}

const columns: Column<ApiKeyOut>[] = [
  { id: "name", header: "Name", cell: (k) => <span className="block truncate" title={k.name}>{k.name}</span> },
  { id: "prefix", header: "Prefix", cell: (k) => <code className="text-xs">{k.prefix}…</code>, width: "9rem" },
  {
    id: "scopes",
    header: "Scopes",
    cell: (k) => (
      <ul className="flex flex-wrap gap-1" aria-label="Scopes">
        {k.scopes.map((s) => (
          <li key={s} className="rounded bg-muted px-1.5 py-0.5 text-xs">{s}</li>
        ))}
      </ul>
    ),
  },
  { id: "expires", header: "Expires", cell: (k) => <Expires iso={k.expires_at} />, width: "10rem" },
  { id: "actions", header: "Actions", cell: (k) => <Revoke k={k} />, width: "6rem" },
];

export default function ApiKeysPage() {
  const q = useApiKeys();
  const mobile = useMediaQuery("(max-width: 767px)");
  const [secret, setSecret] = useState<string | null>(null);
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">API keys</h1>
        <ApiKeyForm
          onKey={setSecret}
          trigger={<button type="button" className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring">New API key</button>}
        />
      </div>
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : (
        <VirtualTable
          label="API keys"
          rows={q.rows}
          columns={columns}
          rowHeight={mobile ? 240 : 64}
          getRowId={(k) => k.id}
          onEndReached={() => {
            if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
          }}
          empty={<EmptyState title="No API keys" hint="Create a key for scripts and metrics scraping." />}
        />
      )}
      <KeyRevealDialog secret={secret} onClose={() => setSecret(null)} />
    </div>
  );
}
