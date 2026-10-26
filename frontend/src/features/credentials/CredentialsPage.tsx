import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Truncate } from "@/components/ui/truncate";
import { isAdmin, useMe } from "../../api/me";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { SharingDialog } from "../../components/common/SharingDialog";
import { VisibilityBadge } from "../../components/common/VisibilityBadge";
import { CredentialForm } from "./CredentialForm";
import { useCredentials, useDeleteCredential, type CredentialOut } from "./hooks";

function Actions({ c }: { c: CredentialOut }) {
  const del = useDeleteCredential();
  const me = useMe().data;
  const owns = me != null && (me.id === c.owner_id || isAdmin(me));
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {owns && <SharingDialog resource="credentials" id={c.id} ownerId={c.owner_id} name={c.name} />}
      {c.can_edit && (
        <CredentialForm
          credential={c}
          trigger={
            <Button size="sm" variant="outline" aria-label={`Edit ${c.name}`}>
              Edit
            </Button>
          }
        />
      )}
      {owns && (
        <ConfirmDialog
          title={`Delete ${c.name}?`}
          body="Sources and notifications using this credential will lose access."
          confirmLabel="Delete"
          destructive
          onConfirm={() => del.mutateAsync(c.id).then(() => undefined)}
          trigger={
            <Button size="sm" variant="outline" aria-label={`Delete ${c.name}`}>
              Delete
            </Button>
          }
        />
      )}
    </div>
  );
}

export default function CredentialsPage() {
  const q = useCredentials();
  return (
    <>
      <PageHeader
        title="Credentials"
        description="Site logins, cookies and notification URLs. Secrets are write-only."
        actions={
          <CredentialForm
            trigger={
              <Button>
                <Plus aria-hidden /> Add credential
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
        <EmptyState title="No credentials yet" hint="Add site logins, cookies or notification URLs." />
      ) : (
        <>
          <Card className="overflow-hidden">
            <Table aria-label="Credentials">
              <TableHeader>
                <TableRow className="h-11 hover:bg-transparent">
                  <TableHead>Name</TableHead>
                  <TableHead>Site</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Visibility</TableHead>
                  <TableHead>Secret</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.rows.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="max-w-56 py-3 font-medium">
                      <Truncate>{c.name}</Truncate>
                    </TableCell>
                    <TableCell className="max-w-56 py-3">
                      <Truncate>{c.site}</Truncate>
                    </TableCell>
                    <TableCell className="py-3 font-mono text-xs">{c.kind}</TableCell>
                    <TableCell className="py-3">
                      <VisibilityBadge visibility={c.visibility} />
                    </TableCell>
                    <TableCell className="py-3">
                      {c.has_secret ? (
                        <Badge tone="success" dot>
                          Secret saved
                        </Badge>
                      ) : (
                        <Badge tone="warning" dot>
                          No secret
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="py-3">
                      <Actions c={c} />
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
    </>
  );
}
