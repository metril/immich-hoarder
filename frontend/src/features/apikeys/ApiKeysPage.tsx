import { useState } from "react";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Truncate } from "@/components/ui/truncate";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { formatRelative } from "../../components/common/formatRelative";
import { ApiKeyForm } from "./ApiKeyForm";
import { ApiKeyEdit } from "./ApiKeyEdit";
import { useApiKeys, useRevokeApiKey, useRotateApiKey, type ApiKeyOut } from "./hooks";
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
        <Button size="sm" variant="outline" aria-label={`Revoke ${k.name}`}>
          Revoke
        </Button>
      }
    />
  );
}

function Rotate({ k, onKey }: { k: ApiKeyOut; onKey: (plaintext: string) => void }) {
  const rotate = useRotateApiKey(onKey);
  return (
    <ConfirmDialog
      title={`Rotate ${k.name}?`}
      body="A new key with the same name, scopes and expiry is issued and this one stops working immediately."
      confirmLabel="Rotate"
      onConfirm={() => rotate.mutateAsync(k.id).then(() => undefined)}
      trigger={
        <Button size="sm" variant="outline" aria-label={`Rotate ${k.name}`}>
          Rotate
        </Button>
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

export default function ApiKeysPage() {
  const q = useApiKeys();
  const [secret, setSecret] = useState<string | null>(null);
  return (
    <>
      <PageHeader
        title="API Keys"
        description="Keys for scripts and metrics scraping."
        actions={
          <ApiKeyForm
            onKey={setSecret}
            trigger={
              <Button>
                <Plus aria-hidden /> New API key
              </Button>
            }
          />
        }
      />
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : q.rows.length === 0 ? (
        <EmptyState title="No API keys" hint="Create a key for scripts and metrics scraping." />
      ) : (
        <>
          <Card className="overflow-hidden">
            <Table aria-label="API keys">
              <TableHeader>
                <TableRow className="h-11 hover:bg-transparent">
                  <TableHead>Name</TableHead>
                  <TableHead>Prefix</TableHead>
                  <TableHead>Scopes</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.rows.map((k) => (
                  <TableRow key={k.id} className="h-auto">
                    <TableCell className="max-w-56 py-3 font-medium">
                      <Truncate>{k.name}</Truncate>
                    </TableCell>
                    <TableCell className="py-3">
                      <code className="font-mono text-xs">{k.prefix}…</code>
                    </TableCell>
                    <TableCell className="min-w-56 py-3">
                      <ul className="flex flex-wrap gap-1.5" aria-label="Scopes">
                        {k.scopes.map((s) => (
                          <li key={s}>
                            <Badge className="font-mono">{s}</Badge>
                          </li>
                        ))}
                      </ul>
                    </TableCell>
                    <TableCell className="whitespace-nowrap py-3">
                      <Expires iso={k.expires_at} />
                    </TableCell>
                    <TableCell className="py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <ApiKeyEdit
                          k={k}
                          trigger={
                            <Button size="sm" variant="outline" aria-label={`Edit ${k.name}`}>
                              Edit
                            </Button>
                          }
                        />
                        <Rotate k={k} onKey={setSecret} />
                        <Revoke k={k} />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          {q.hasNextPage && (
            <div className="flex justify-center">
              <Button variant="outline" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
      <KeyRevealDialog secret={secret} onClose={() => setSecret(null)} />
    </>
  );
}
