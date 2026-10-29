import { toast } from "sonner";
import { useEffect, useMemo, useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { MoreHorizontal, Search } from "lucide-react";
import { isAdmin, useMe } from "../../api/me";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { SharingDialog } from "../../components/common/SharingDialog";
import { useMediaQuery } from "../../components/common/useMediaQuery";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";
import { VisibilityBadge } from "../../components/common/VisibilityBadge";
import { Menu, MenuItem } from "../../components/shell/Menu";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { PageHeader } from "../../components/ui/page";
import { Switch } from "../../components/ui/switch";
import { Truncate } from "../../components/ui/truncate";
import { useTargets } from "../targets/hooks";
import { PreviewPanel } from "./PreviewPanel";
import { RipDialog } from "./RipDialog";
import { RunDialog } from "./RunDialog";
import { SourceSheet } from "./SourceSheet";
import { useDeleteSource, useForgetSeen, useSources, useToggleSource, type SourceIn, type SourceOut } from "./hooks";

const route = getRouteApi("/_app/sources");

type Cronstrue = typeof import("cronstrue").default;
let cronLib: Cronstrue | null = null;

/** Human cron text; cronstrue is loaded lazily (raw cron shown until it arrives). */
function Schedule({ cron }: { cron: string | null }) {
  const [lib, setLib] = useState<{ c: Cronstrue } | null>(cronLib ? { c: cronLib } : null);
  useEffect(() => {
    if (!cron || lib) return;
    let live = true;
    void import("cronstrue").then((m) => {
      cronLib = m.default;
      if (live) setLib({ c: m.default });
    });
    return () => { live = false; };
  }, [cron, lib]);
  if (!cron) return <Truncate>Manual</Truncate>;
  let text = cron;
  if (lib) {
    try {
      text = lib.c.toString(cron, { use24HourTimeFormat: true, verbose: false });
    } catch { /* keep raw */ }
  }
  return <Truncate title={cron}>{text}</Truncate>;
}

function draftOf(s: SourceOut): SourceIn {
  return {
    name: s.name, url: s.url, target_id: s.target_id, credential_id: s.credential_id, album_template: s.album_template,
    schedule_cron: s.schedule_cron, backfill_mode: s.backfill_mode, backfill_value: s.backfill_value,
    allow_animated: s.allow_animated, filters: s.filters, notify: s.notify, gdl_options: s.gdl_options,
    proxy: s.proxy, log_level: s.log_level, enabled: s.enabled, ephemeral: s.ephemeral, visibility: s.visibility,
  };
}

function PreviewDialog({ s, open, onOpenChange }: { s: SourceOut; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="min-w-0"><Truncate>Dry run · {s.name}</Truncate></DialogTitle>
          <DialogDescription>Lists what the source would fetch, without downloading anything.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <PreviewPanel draft={draftOf(s)} />
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Close</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EnabledSwitch({ s }: { s: SourceOut }) {
  const toggle = useToggleSource();
  return (
    <Switch
      aria-label={`Enabled ${s.name}`}
      checked={s.enabled}
      disabled={!s.can_edit}
      onCheckedChange={(v) => toggle.mutate({ id: s.id, enabled: v })}
    />
  );
}

function Actions({ s }: { s: SourceOut }) {
  const del = useDeleteSource();
  const forget = useForgetSeen();
  const [confirmForget, setConfirmForget] = useState(false);
  const me = useMe().data;
  const navigate = useNavigate();
  const [preview, setPreview] = useState(false);
  const [share, setShare] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const owns = me != null && (me.id === s.owner_id || isAdmin(me));
  return (
    <div className="flex items-center gap-2">
      {s.can_use && <RunDialog sourceId={s.id} name={s.name} />}
      <Menu label={`More actions for ${s.name}`} trigger={<MoreHorizontal className="size-4" aria-hidden />}>
        <MenuItem aria-label={`Preview ${s.name}`} onAction={() => setPreview(true)}>Preview</MenuItem>
        {owns && <MenuItem aria-label={`Share ${s.name}`} onAction={() => setShare(true)}>Share</MenuItem>}
        {s.can_edit && (
          <MenuItem aria-label={`Edit ${s.name}`} onAction={() => void navigate({ to: "/sources", search: (p) => ({ ...p, edit: s.id }) })}>Edit</MenuItem>
        )}
        {s.can_edit && <MenuItem aria-label={`Forget seen URLs for ${s.name}`} onAction={() => setConfirmForget(true)}>Forget seen URLs</MenuItem>}
        {owns && <MenuItem aria-label={`Delete ${s.name}`} className="text-destructive" onAction={() => setConfirm(true)}>Delete</MenuItem>}
      </Menu>
      <PreviewDialog s={s} open={preview} onOpenChange={setPreview} />
      {owns && <SharingDialog resource="sources" id={s.id} ownerId={s.owner_id} name={s.name} open={share} onOpenChange={setShare} hideTrigger />}
      {s.can_edit && (
        <ConfirmDialog
          open={confirmForget}
          onOpenChange={setConfirmForget}
          title={`Forget seen URLs for ${s.name}?`}
          body="The next run re-processes every item, re-linking assets the target already has. Deletions in Immich are not undone. Not allowed while a job is active."
          confirmLabel="Forget"
          onConfirm={() =>
            forget.mutateAsync(s.id).then((r) => {
              toast.success(`Forgot ${r.forgotten} seen URL${r.forgotten === 1 ? "" : "s"}`);
            })
          }
        />
      )}
      {owns && (
        <ConfirmDialog
          open={confirm}
          onOpenChange={setConfirm}
          title={`Delete ${s.name}?`}
          body="Its schedule is removed. A source with an active job cannot be deleted."
          confirmLabel="Delete"
          destructive
          onConfirm={() => del.mutateAsync(s.id).then(() => undefined)}
        />
      )}
    </div>
  );
}

export default function SourcesPage() {
  const search = route.useSearch();
  const navigate = useNavigate();
  const q = useSources();
  const targets = useTargets();
  const mobile = useMediaQuery("(max-width: 767px)");
  const [filter, setFilter] = useState(search.q ?? "");
  const [rip, setRip] = useState(false);

  const targetName = useMemo(() => new Map(targets.rows.map((t) => [t.id, t.name])), [targets.rows]);
  const rows = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return f ? q.rows.filter((s) => `${s.name} ${s.url} ${s.extractor}`.toLowerCase().includes(f)) : q.rows;
  }, [q.rows, filter]);

  const columns: Column<SourceOut>[] = [
    { id: "name", header: "Name", cell: (s) => <Truncate className="font-medium">{s.name}</Truncate>, width: "minmax(16rem,2fr)" },
    { id: "ext", header: "Extractor", cell: (s) => <Badge className="font-mono">{s.extractor}</Badge>, width: "7rem" },
    { id: "target", header: "Target", cell: (s) => <Truncate>{targetName.get(s.target_id) ?? `Target #${s.target_id}`}</Truncate>, width: "minmax(0,1fr)", hideBelow: "md" },
    { id: "sched", header: "Schedule", cell: (s) => <Schedule cron={s.schedule_cron} />, width: "minmax(0,1fr)" },
    { id: "enabled", header: "Enabled", cell: (s) => <EnabledSwitch s={s} />, width: "6rem" },
    { id: "vis", header: "Visibility", cell: (s) => <VisibilityBadge visibility={s.visibility} />, width: "7rem" },
    { id: "actions", header: "Actions", cell: (s) => <Actions s={s} />, width: "8rem" },
  ];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Sources"
        actions={
          <>
            <div className="relative w-full sm:w-auto">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                data-page-search
                type="search"
                aria-label="Search sources"
                placeholder="Search loaded sources…"
                className="w-full min-w-0 pl-9 sm:w-64"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <Button variant="outline" onClick={() => setRip(true)}>
              Ad-hoc rip
            </Button>
            <Button data-new-action onClick={() => void navigate({ to: "/sources", search: (p) => ({ ...p, new: true }) })}>
              New source
            </Button>
          </>
        }
      />
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : (
        <VirtualTable
          label="Sources"
          minWidth="min-w-[60rem]"
          rows={rows}
          columns={columns}
          rowHeight={mobile ? 340 : 56}
          getRowId={(s) => s.id}
          onEndReached={() => {
            if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
          }}
          empty={<EmptyState title={filter ? "No matching sources" : "No sources yet"} hint={filter ? "Try a different search." : "Add a source to start collecting."} />}
        />
      )}
      <SourceSheet
        edit={search.edit}
        isNew={search.new}
        rows={q.rows}
        onClose={() => void navigate({ to: "/sources", search: (p) => ({ ...p, edit: undefined, new: undefined }) })}
      />
      <RipDialog open={rip} onOpenChange={setRip} />
    </div>
  );
}
