import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "../../api/client";
import { ApiError, unwrap } from "../../api/errors";
import { useMe } from "../../api/me";
import type { components } from "../../api/schema";
import { EmptyState } from "../../components/common/EmptyState";
import { flatItems, useCursorList } from "../../components/common/useCursorList";
import { useMediaQuery } from "../../components/common/useMediaQuery";
import { VirtualTable, type Column } from "../../components/common/VirtualTable";

type UserOut = components["schemas"]["UserOut"];

function useSetDisabled() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, disabled }: { id: number; disabled: boolean }) =>
      unwrap(await api.PATCH("/api/v1/users/{user_id}", { params: { path: { user_id: id } }, body: { disabled } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ["list", "users"] }),
  });
}

function DisabledSwitch({ u }: { u: UserOut }) {
  const me = useMe().data;
  const set = useSetDisabled();
  const [pending, setPending] = useState<boolean | null>(null); // optimistic value; reverts on failure
  const checked = pending ?? u.disabled;
  const toggle = () => {
    const next = !checked;
    setPending(next);
    set.mutate(
      { id: u.id, disabled: next },
      {
        onError: (e) => toast.error(e instanceof ApiError && e.status === 409 && e.message === "last admin" ? "Cannot disable the last admin" : e.message),
        onSettled: () => setPending(null),
      },
    );
  };
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={`Disabled: ${u.name ?? u.sub}`}
      disabled={me?.id === u.id || set.isPending}
      onClick={toggle}
      className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50 ${checked ? "bg-destructive" : "bg-muted"}`}
    >
      <span className={`absolute left-0.5 top-0.5 size-4 rounded-full bg-background shadow transition-transform ${checked ? "translate-x-5" : ""}`} />
    </button>
  );
}

const columns: Column<UserOut>[] = [
  { id: "name", header: "Name", cell: (u) => <span className="block truncate">{u.name ?? u.sub}</span> },
  { id: "email", header: "Email", cell: (u) => <span className="block truncate">{u.email ?? "—"}</span> },
  {
    id: "role",
    header: "Role",
    cell: (u) => (
      <span className={`rounded px-1.5 py-0.5 text-xs ${u.role === "admin" ? "bg-primary text-primary-foreground" : "bg-muted"}`}>{u.role}</span>
    ),
    width: "6rem",
  },
  { id: "groups", header: "Groups", cell: (u) => <span className="block truncate">{u.groups.join(", ") || "—"}</span> },
  { id: "disabled", header: "Disabled", cell: (u) => <DisabledSwitch u={u} />, width: "6rem" },
];

export default function UsersPage() {
  const q = useCursorList("users", "/api/v1/users");
  const rows = flatItems(q);
  const mobile = useMediaQuery("(max-width: 767px)");
  return (
    <div className="space-y-4 p-4">
      <h1 className="text-xl font-semibold">Users</h1>
      <p className="text-sm text-muted-foreground">Roles come from OIDC groups; you can only enable or disable accounts here.</p>
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : (
        <VirtualTable
          label="Users"
          rows={rows}
          columns={columns}
          rowHeight={mobile ? 240 : 56}
          getRowId={(u) => u.id}
          onEndReached={() => {
            if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
          }}
          empty={<EmptyState title="No users" hint="Users appear after their first sign-in." />}
        />
      )}
    </div>
  );
}
