import { useEffect, useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../../api/client";
import { ApiError, unwrap } from "../../api/errors";
import { keys, type Resource } from "../../api/keys";
import { isAdmin, useMe } from "../../api/me";
import type { components } from "../../api/schema";
import { Button } from "../ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { Truncate } from "../ui/truncate";

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
      <Input
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
      />
      {results.length > 0 && (
        <ul id={listId} role="listbox" aria-label="Users" className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded-lg border bg-popover p-1 shadow-md">
          {results.map((u, i) => (
            <li
              key={u.id}
              id={optId(i)}
              role="option"
              aria-selected={i === activeIdx}
              className={`cursor-pointer rounded-md px-2.5 py-2 text-sm hover:bg-accent ${i === activeIdx ? "bg-accent" : ""}`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(u)}
            >
              <Truncate>{u.name ?? `User #${u.id}`}</Truncate>
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

  if (q.isPending) return <DialogBody><p className="text-sm text-muted-foreground">Loading…</p></DialogBody>;
  if (q.isError) return <DialogBody><p role="alert" className="text-sm text-destructive">Failed to load sharing.</p></DialogBody>;

  return (
    <>
      <DialogBody className="grid gap-6">
        <fieldset className="grid gap-2">
          <legend className="mb-2 text-sm font-medium">Visibility</legend>
          {VIS.map((o) => (
            <label key={o.v} className="flex items-center gap-2 text-sm">
              <input type="radio" name={`vis-${id}`} checked={visibility === o.v} onChange={() => setVis(o.v)} />
              {o.label}
            </label>
          ))}
        </fieldset>

        <fieldset disabled={!restricted} className="grid gap-4 disabled:opacity-50">
          <legend className="mb-2 text-sm font-medium">Shared with</legend>
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
            <Input aria-label="Add group" list={groupList} placeholder="Group name" value={group} onChange={(e) => setGroup(e.target.value)} />
            <datalist id={groupList}>
              {(me?.groups ?? []).map((g) => (
                <option key={g} value={g} />
              ))}
            </datalist>
            <Button type="submit" variant="outline">
              Add
            </Button>
          </form>
          <ul className="grid gap-2">
            {list.map((e) => {
              const name = label(e);
              return (
                <li key={`${e.principal_type}:${e.principal_id}`} className="flex items-center gap-2 text-sm">
                  <Truncate className="flex-1">{name}</Truncate>
                  <Select
                    aria-label={`Permission for ${name}`}
                    value={e.perm}
                    onChange={(ev) => setEntries(list.map((x) => (x === e ? { ...x, perm: ev.target.value as Entry["perm"] } : x)))}
                    className="h-8 w-24 shrink-0"
                  >
                    <option value="use">use</option>
                    <option value="edit">edit</option>
                  </Select>
                  <Button variant="ghost" size="sm" aria-label={`Remove ${name}`} onClick={() => setEntries(list.filter((x) => x !== e))}>
                    Remove
                  </Button>
                </li>
              );
            })}
            {list.length === 0 && <li className="text-sm text-muted-foreground">Nobody yet.</li>}
          </ul>
        </fieldset>

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </DialogBody>
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="outline">Cancel</Button>
        </DialogClose>
        <Button
          loading={save.isPending}
          onClick={() => {
            setError(null);
            save.mutate();
          }}
        >
          Save
        </Button>
      </DialogFooter>
    </>
  );
}

export function SharingDialog({
  resource,
  id,
  ownerId,
  open: openProp,
  onOpenChange,
  hideTrigger,
}: {
  resource: Extract<Resource, ShareResource>;
  id: number;
  ownerId: number;
  /** Controlled mode (e.g. opened from a menu item); set hideTrigger to drop the built-in button. */
  open?: boolean;
  onOpenChange?: (o: boolean) => void;
  hideTrigger?: boolean;
}) {
  const { data: me } = useMe();
  const [inner, setInner] = useState(false);
  const open = openProp ?? inner;
  const setOpen = onOpenChange ?? setInner;
  if (!me || !(me.id === ownerId || isAdmin(me))) return null;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {hideTrigger ? null : (
        <DialogTrigger asChild>
          <Button variant="outline" size="sm">Share</Button>
        </DialogTrigger>
      )}
      <DialogContent aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Sharing</DialogTitle>
        </DialogHeader>
        <Editor resource={resource} id={id} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}
