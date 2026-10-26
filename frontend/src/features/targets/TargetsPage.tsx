import { useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Truncate } from "@/components/ui/truncate";
import { isAdmin, useMe } from "../../api/me";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { SharingDialog } from "../../components/common/SharingDialog";
import { VisibilityBadge } from "../../components/common/VisibilityBadge";
import { AlbumsList } from "./AlbumsList";
import { TargetForm } from "./TargetForm";
import { TargetTestButton } from "./TargetTestButton";
import { useDeleteTarget, useTargets, type TargetOut } from "./hooks";

const route = getRouteApi("/_app/targets");

function AlbumsSheet({ t }: { t: TargetOut }) {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="sm" variant="outline" aria-label={`Albums of ${t.name}`}>
          Albums
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle className="break-words">Albums · {t.name}</SheetTitle>
          <SheetDescription className="sr-only">Albums on this Immich server</SheetDescription>
        </SheetHeader>
        <SheetBody>
          <AlbumsList targetId={t.id} enabled={open} />
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

function TargetCard({ t }: { t: TargetOut }) {
  const del = useDeleteTarget();
  const me = useMe().data;
  const owns = me != null && (me.id === t.owner_id || isAdmin(me));
  return (
    <Card className="flex w-full min-w-0 flex-col">
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <Truncate className="font-display text-base font-semibold">{t.name}</Truncate>
            <Truncate className="mt-1 font-mono text-xs text-muted-foreground">{t.url}</Truncate>
          </div>
          <VisibilityBadge visibility={t.visibility} />
        </div>
        <div className="flex flex-wrap gap-2">
          {t.has_api_key ? (
            <Badge tone="success" dot>
              API key saved
            </Badge>
          ) : (
            <Badge tone="warning" dot>
              No API key
            </Badge>
          )}
        </div>
      </CardContent>
      <CardFooter className="flex-wrap">
        <TargetTestButton id={t.id} name={t.name} />
        <AlbumsSheet t={t} />
        {owns && <SharingDialog resource="targets" id={t.id} ownerId={t.owner_id} name={t.name} />}
        {t.can_edit && (
          <TargetForm
            target={t}
            trigger={
              <Button size="sm" variant="outline" aria-label={`Edit ${t.name}`}>
                Edit
              </Button>
            }
          />
        )}
        {owns && (
          <ConfirmDialog
            title={`Delete ${t.name}?`}
            body="Jobs using this target will stop working."
            confirmLabel="Delete"
            destructive
            onConfirm={() => del.mutateAsync(t.id).then(() => undefined)}
            trigger={
              <Button size="sm" variant="outline" aria-label={`Delete ${t.name}`}>
                Delete
              </Button>
            }
          />
        )}
      </CardFooter>
    </Card>
  );
}

export default function TargetsPage() {
  const q = useTargets();
  const search = route.useSearch();
  const navigate = useNavigate();
  return (
    <>
      <PageHeader
        title="Targets"
        description="Immich servers that jobs upload to."
        actions={
          <TargetForm
            open={search.new === true}
            onOpenChange={(o) => void navigate({ to: "/targets", search: o ? { new: true } : {}, replace: !o })}
            trigger={
              <Button>
                <Plus aria-hidden /> Add target
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
        <EmptyState title="No targets yet" hint="Add an Immich server to upload to." />
      ) : (
        <>
          <ul aria-label="Targets" className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {q.rows.map((t) => (
              <li key={t.id} className="flex min-w-0">
                <TargetCard t={t} />
              </li>
            ))}
          </ul>
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
