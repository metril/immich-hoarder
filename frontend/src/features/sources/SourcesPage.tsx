import { useMemo, useState } from "react";
import { Dialog } from "radix-ui";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import cronstrue from "cronstrue";
import { isAdmin, useMe } from "../../api/me";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { inputClass } from "../../components/common/FormField";
import { SharingDialog } from "../../components/common/SharingDialog";
import { useMediaQuery } from "../../components/common/useMediaQuery";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";
import { VisibilityBadge } from "../../components/common/VisibilityBadge";
import { useTargets } from "../targets/hooks";
import { PreviewPanel } from "./PreviewPanel";
import { RipDialog } from "./RipDialog";
import { RunDialog } from "./RunDialog";
import { SourceSheet } from "./SourceSheet";
import { useDeleteSource, useSources, useToggleSource, type SourceIn, type SourceOut } from "./hooks";

const route = getRouteApi("/_app/sources");
const btn = "rounded-md border px-2 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring";
const primary = "rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring";

function schedule(cron: string | null): string {
  if (!cron) return "Manual";
  try {
    return cronstrue.toString(cron, { use24HourTimeFormat: true, verbose: false });
  } catch {
    return cron;
  }
}

function draftOf(s: SourceOut): SourceIn {
  return {
    name: s.name, url: s.url, target_id: s.target_id, credential_id: s.credential_id, album_template: s.album_template,
    schedule_cron: s.schedule_cron, backfill_mode: s.backfill_mode, backfill_value: s.backfill_value,
    allow_animated: s.allow_animated, filters: s.filters, notify: s.notify, gdl_options: s.gdl_options,
    proxy: s.proxy, log_level: s.log_level, enabled: s.enabled, ephemeral: s.ephemeral, visibility: s.visibility,
  };
}

function PreviewButton({ s }: { s: SourceOut }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger className={btn} aria-label={`Preview ${s.name}`}>Preview</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">Dry run · {s.name}</Dialog.Title>
          <Dialog.Description className="mb-3 text-sm text-muted-foreground">Lists what the source would fetch, without downloading anything.</Dialog.Description>
          <PreviewPanel draft={draftOf(s)} />
          <Dialog.Close className={`${btn} mt-4`}>Close</Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function EnabledSwitch({ s }: { s: SourceOut }) {
  const toggle = useToggleSource();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={s.enabled}
      aria-label={`Enabled ${s.name}`}
      disabled={!s.can_edit}
      onClick={() => toggle.mutate({ id: s.id, enabled: !s.enabled })}
      className={`relative h-5 w-9 rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50 ${s.enabled ? "bg-primary" : "bg-muted"}`}
    >
      <span className={`absolute top-0.5 size-3.5 rounded-full bg-background shadow transition-all ${s.enabled ? "left-4.5" : "left-0.5"}`} />
    </button>
  );
}

function Actions({ s }: { s: SourceOut }) {
  const del = useDeleteSource();
  const me = useMe().data;
  const navigate = useNavigate();
  const owns = me != null && (me.id === s.owner_id || isAdmin(me));
  return (
    <div className="flex flex-wrap gap-1">
      {s.can_use && <RunDialog sourceId={s.id} name={s.name} />}
      <PreviewButton s={s} />
      {owns && <SharingDialog resource="sources" id={s.id} ownerId={s.owner_id} />}
      {s.can_edit && (
        <button type="button" aria-label={`Edit ${s.name}`} className={btn} onClick={() => void navigate({ to: "/sources", search: (p) => ({ ...p, edit: s.id }) })}>
          Edit
        </button>
      )}
      {owns && (
        <ConfirmDialog
          title={`Delete ${s.name}?`}
          body="Its schedule is removed. A source with an active job cannot be deleted."
          confirmLabel="Delete"
          destructive
          onConfirm={() => del.mutateAsync(s.id).then(() => undefined)}
          trigger={<button type="button" aria-label={`Delete ${s.name}`} className={btn}>Delete</button>}
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
    { id: "name", header: "Name", cell: (s) => <span className="block truncate" title={s.name}>{s.name}</span>, width: "minmax(0,1.2fr)" },
    { id: "ext", header: "Extractor", cell: (s) => <span className="rounded-full border px-2 py-0.5 text-xs">{s.extractor}</span>, width: "8rem" },
    { id: "target", header: "Target", cell: (s) => targetName.get(s.target_id) ?? `Target #${s.target_id}`, width: "minmax(0,1fr)", hideBelow: "md" },
    { id: "sched", header: "Schedule", cell: (s) => <span title={s.schedule_cron ?? undefined}>{schedule(s.schedule_cron)}</span>, width: "minmax(0,1fr)" },
    { id: "enabled", header: "Enabled", cell: (s) => <EnabledSwitch s={s} />, width: "6rem" },
    { id: "vis", header: "Visibility", cell: (s) => <VisibilityBadge visibility={s.visibility} />, width: "8rem" },
    { id: "actions", header: "Actions", cell: (s) => <Actions s={s} />, width: "20rem" },
  ];

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Sources</h1>
        <div className="flex gap-2">
          <button type="button" className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring" onClick={() => setRip(true)}>
            Ad-hoc rip
          </button>
          <button type="button" data-new-action className={primary} onClick={() => void navigate({ to: "/sources", search: (p) => ({ ...p, new: true }) })}>
            New source
          </button>
        </div>
      </div>
      <input
        data-page-search
        type="search"
        aria-label="Search sources"
        placeholder="Search loaded sources…"
        className={inputClass}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : (
        <VirtualTable
          label="Sources"
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
