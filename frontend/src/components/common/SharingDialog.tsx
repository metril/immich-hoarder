import { useEffect, useId, useState } from "react";
import { Dialog } from "radix-ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../../api/client";
import { ApiError, unwrap } from "../../api/errors";
import { keys, type Resource } from "../../api/keys";
import { isAdmin, useMe } from "../../api/me";
import type { components } from "../../api/schema";
import { inputClass } from "./FormField";

type Visibility = components["schemas"]["Visibility"];
type Entry = components["schemas"]["ShareEntry"];
type SharesBody = components["schemas"]["SharesBody"];
type ShareResource = "targets" | "credentials" | "sources";

const VIS: { v: Visibility; label: string }[] = [
  { v: "private", label: "Private" },
  { v: "everyone", label: "Everyone" },
  { v: "restricted", label: "Restricted" },
];

function useDebounced<T>(value: T, ms: number): T {
  const [d, setD] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setD(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return d;
}

async function getShares(resource: ShareResource, id: number): Promise<SharesBody> {
  const p = { params: { path: { obj_id: id } } };
  if (resource === "targets") return unwrap(await api.GET("/api/v1/targets/{obj_id}/shares", p));
  if (resource === "credentials") return unwrap(await api.GET("/api/v1/credentials/{obj_id}/shares", p));
  return unwrap(await api.GET("/api/v1/sources/{obj_id}/shares", p));
}

async function putShares(resource: ShareResource, id: number, body: SharesBody): Promise<SharesBody> {
  const p = { params: { path: { obj_id: id } }, body };
  if (resource === "targets") return unwrap(await api.PUT("/api/v1/targets/{obj_id}/shares", p));
  if (resource === "credentials") return unwrap(await api.PUT("/api/v1/credentials/{obj_id}/shares", p));
  return unwrap(await api.PUT("/api/v1/sources/{obj_id}/shares", p));
}

function UserPicker({ onPick }: { onPick: (u: { id: number; name: string | null }) => void }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 250);
  const listId = useId();
  const res = useQuery({
    queryKey: keys.directory(dq),
    enabled: dq.length >= 2,
    queryFn: async () => unwrap(await api.GET("/api/v1/users/directory", { params: { query: { q: dq } } })),
  });
  const results = dq.length >= 2 ? (res.data ?? []) : [];
  const [active, setActive] = useState(-1);
  const activeIdx = active >= 0 && active < results.length ? active : -1;
  const optId = (i: number) => `${listId}-o${i}`;
  const pick = (u: { id: number; name: string | null }) => {
    onPick(u);
    setQ("");
    setActive(-1);
  };
  return (
    <div className="relative">
      <input
        role="combobox"
        aria-label="Add user"
        aria-expanded={results.length > 0}
        aria-controls={listId}
        aria-activedescendant={activeIdx >= 0 ? optId(activeIdx) : undefined}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="Search users (name or exact email)"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setActive(-1);
        }}
        onKeyDown={(e) => {
          if (results.length === 0) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((activeIdx + 1) % results.length);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((activeIdx - 1 + results.length) % results.length);
          } else if (e.key === "Enter" && activeIdx >= 0) {
            e.preventDefault();
            const u = results[activeIdx];
            if (u) pick(u);
          } else if (e.key === "Escape") {
            setQ("");
          }
        }}
        className={inputClass}
      />
      {results.length > 0 && (
        <ul id={listId} role="listbox" aria-label="Users" className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md">
          {results.map((u, i) => (
            <li
              key={u.id}
              id={optId(i)}
              role="option"
              aria-selected={i === activeIdx}
              className={`cursor-pointer rounded px-2 py-1.5 text-sm hover:bg-accent ${i === activeIdx ? "bg-accent" : ""}`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(u)}
            >
              {u.name ?? `User #${u.id}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Editor({ resource, id, onDone }: { resource: ShareResource; id: number; onDone: () => void }) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: keys.shares(resource, id), queryFn: () => getShares(resource, id) });
  const [vis, setVis] = useState<Visibility | null>(null);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [group, setGroup] = useState("");
  const [error, setError] = useState<string | null>(null);
  const groupList = useId();

  const visibility = vis ?? q.data?.visibility ?? "private";
  const list = entries ?? q.data?.shares ?? [];
  const restricted = visibility === "restricted";

  const save = useMutation({
    mutationFn: () => putShares(resource, id, { visibility, shares: restricted ? list : [] }),
    onSuccess: (d) => {
      qc.setQueryData(keys.shares(resource, id), d);
      void qc.invalidateQueries({ queryKey: ["list", resource] });
      toast.success("Sharing updated");
      onDone();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to save"),
  });

  const add = (e: Entry) => {
    if (list.some((x) => x.principal_type === e.principal_type && x.principal_id === e.principal_id)) return;
    setEntries([...list, e]);
  };
  const label = (e: Entry) =>
    e.principal_type === "user"
      ? (names[e.principal_id] ?? e.principal_name ?? `User #${e.principal_id}`)
      : `Group: ${e.principal_name ?? e.principal_id}`;

  if (q.isPending) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (q.isError) return <p role="alert" className="text-sm text-destructive">Failed to load sharing.</p>;

  return (
    <div className="grid gap-4">
      <fieldset className="grid gap-1">
        <legend className="mb-1 text-sm font-medium">Visibility</legend>
        {VIS.map((o) => (
          <label key={o.v} className="flex items-center gap-2 text-sm">
            <input type="radio" name={`vis-${id}`} checked={visibility === o.v} onChange={() => setVis(o.v)} />
            {o.label}
          </label>
        ))}
      </fieldset>

      <fieldset disabled={!restricted} className="grid gap-3 disabled:opacity-50">
        <legend className="mb-1 text-sm font-medium">Shared with</legend>
        <UserPicker
          onPick={(u) => {
            setNames((n) => ({ ...n, [String(u.id)]: u.name ?? `User #${u.id}` }));
            add({ principal_type: "user", principal_id: String(u.id), perm: "use" });
          }}
        />
        <form
          className="flex gap-2"
          onSubmit={(ev) => {
            ev.preventDefault();
            const g = group.trim();
            if (g) add({ principal_type: "group", principal_id: g, perm: "use" });
            setGroup("");
          }}
        >
          <input
            aria-label="Add group"
            list={groupList}
            placeholder="Group name"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            className={inputClass}
          />
          <datalist id={groupList}>
            {(me?.groups ?? []).map((g) => (
              <option key={g} value={g} />
            ))}
          </datalist>
          <button type="submit" className="rounded-md border px-3 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
            Add
          </button>
        </form>
        <ul className="grid gap-1">
          {list.map((e) => {
            const name = label(e);
            return (
              <li key={`${e.principal_type}:${e.principal_id}`} className="flex items-center gap-2 text-sm">
                <span className="min-w-0 flex-1 truncate">{name}</span>
                <select
                  aria-label={`Permission for ${name}`}
                  value={e.perm}
                  onChange={(ev) =>
                    setEntries(
                      list.map((x) => (x === e ? { ...x, perm: ev.target.value as Entry["perm"] } : x)),
                    )
                  }
                  className="h-8 rounded-md border bg-background px-2 text-sm"
                >
                  <option value="use">use</option>
                  <option value="edit">edit</option>
                </select>
                <button
                  type="button"
                  aria-label={`Remove ${name}`}
                  onClick={() => setEntries(list.filter((x) => x !== e))}
                  className="rounded-md border px-2 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
                >
                  Remove
                </button>
              </li>
            );
          })}
          {list.length === 0 && <li className="text-sm text-muted-foreground">Nobody yet.</li>}
        </ul>
      </fieldset>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Dialog.Close className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
          Cancel
        </Dialog.Close>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => {
            setError(null);
            save.mutate();
          }}
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </div>
  );
}

export function SharingDialog({ resource, id, ownerId }: { resource: Extract<Resource, ShareResource>; id: number; ownerId: number }) {
  const { data: me } = useMe();
  const [open, setOpen] = useState(false);
  if (!me || !(me.id === ownerId || isAdmin(me))) return null;
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
        Share
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl"
        >
          <Dialog.Title className="mb-3 text-base font-semibold">Sharing</Dialog.Title>
          <Editor resource={resource} id={id} onDone={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
