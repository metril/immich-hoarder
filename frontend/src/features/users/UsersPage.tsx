import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "../../api/client";
import { ApiError, unwrap } from "../../api/errors";
import { useMe } from "../../api/me";
import { EmptyState } from "../../components/common/EmptyState";
import { flatItems, useCursorList } from "../../components/common/useCursorList";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Truncate } from "@/components/ui/truncate";
import { CreateUserDialog, DeleteUserDialog, ResetPasswordDialog, type UserOut } from "./UserDialogs";

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
    <Switch
      aria-label={`Disabled: ${u.name ?? u.sub}`}
      checked={checked}
      disabled={me?.id === u.id || set.isPending}
      onCheckedChange={toggle}
      className="data-[state=checked]:bg-destructive"
    />
  );
}

const initials = (n: string) =>
  n
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("") || "?";

export default function UsersPage() {
  const q = useCursorList("users", "/api/v1/users");
  const rows = flatItems(q);
  const me = useMe().data;
  const [creating, setCreating] = useState(false);
  const [resetting, setResetting] = useState<UserOut | null>(null);
  const [deleting, setDeleting] = useState<UserOut | null>(null);
  return (
    <>
      <PageHeader
        title="Users"
        description="OIDC roles come from groups; local accounts are managed here."
        actions={<Button onClick={() => setCreating(true)}>New local user</Button>}
      />
      <CreateUserDialog open={creating} onOpenChange={setCreating} />
      <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />
      <DeleteUserDialog user={deleting} others={rows} onClose={() => setDeleting(null)} />
      {q.isPending ? (
        <p role="status">Loading…</p>
      ) : q.isError ? (
        <p role="alert" className="text-destructive">{q.error.message}</p>
      ) : rows.length === 0 ? (
        <EmptyState title="No users" hint="Users appear after their first sign-in." />
      ) : (
        <>
          <Card className="overflow-hidden">
            <Table aria-label="Users">
              <TableHeader>
                <TableRow className="h-11 hover:bg-transparent">
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Groups</TableHead>
                  <TableHead>Disabled</TableHead>
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="max-w-60 py-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span
                          aria-hidden
                          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-accent-foreground"
                        >
                          {initials(u.name ?? u.sub)}
                        </span>
                        <Truncate className="font-medium">{u.name ?? u.sub}</Truncate>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-60 py-3">
                      <Truncate>{u.email ?? "—"}</Truncate>
                    </TableCell>
                    <TableCell className="py-3">
                      <Badge tone={u.role === "admin" ? "primary" : "neutral"}>{u.role}</Badge>
                    </TableCell>
                    <TableCell className="max-w-60 py-3">
                      <Truncate>{u.groups.join(", ") || "—"}</Truncate>
                    </TableCell>
                    <TableCell className="py-3">
                      <DisabledSwitch u={u} />
                    </TableCell>
                    <TableCell className="py-3">
                      {u.sub.startsWith("local:") && (
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" aria-label={`Reset password: ${u.name ?? u.sub}`} onClick={() => setResetting(u)}>
                            Reset password
                          </Button>
                          <Button size="sm" variant="outline" aria-label={`Delete: ${u.name ?? u.sub}`} disabled={me?.id === u.id} onClick={() => setDeleting(u)}>
                            Delete
                          </Button>
                        </div>
                      )}
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
