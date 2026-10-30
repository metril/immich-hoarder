import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import type { components } from "../../api/schema";
import { FormField, FormRootError } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

export type UserOut = components["schemas"]["UserOut"];
type OwnedCounts = components["schemas"]["OwnedCounts"];

const MIN = 8;
const invalidate = (qc: ReturnType<typeof useQueryClient>) => qc.invalidateQueries({ queryKey: ["list", "users"] });

const createSchema = z.object({
  username: z.string().trim().min(1, "Username is required").max(64),
  password: z.string().min(MIN, `At least ${MIN} characters`),
  role: z.enum(["user", "admin"]),
  must_change_password: z.boolean(),
});

export function CreateUserDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const form = useApiForm(createSchema, {
    defaultValues: { username: "", password: "", role: "user", must_change_password: false },
    onSubmit: async (v) => {
      unwrap(await api.POST("/api/v1/users/local", { body: v }));
      await invalidate(qc);
      toast.success(`Created ${v.username}`);
      form.reset();
      onOpenChange(false);
    },
  });
  const e = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New local user</DialogTitle>
          <DialogDescription>Creates an account that signs in with a username and password.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
          <DialogBody className="grid gap-4">
            <FormField label="Username" error={e.username?.message}>
              <Input autoComplete="off" {...form.register("username")} />
            </FormField>
            <FormField label="Password" error={e.password?.message} hint={`At least ${MIN} characters`}>
              <Input type="password" autoComplete="new-password" {...form.register("password")} />
            </FormField>
            <FormField label="Role" error={e.role?.message}>
              <Select {...form.register("role")}>
                <option value="user">user</option>
                <option value="admin">admin</option>
              </Select>
            </FormField>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4" {...form.register("must_change_password")} />
              Require a password change at first sign-in
            </label>
            <FormRootError message={form.rootError} />
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button type="submit" loading={form.formState.isSubmitting}>
              Create user
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const resetSchema = z.object({
  new_password: z.string().min(MIN, `At least ${MIN} characters`),
  must_change_password: z.boolean(),
});

export function ResetPasswordDialog({ user, onClose }: { user: UserOut | null; onClose: () => void }) {
  const qc = useQueryClient();
  const form = useApiForm(resetSchema, {
    defaultValues: { new_password: "", must_change_password: true },
    onSubmit: async (v) => {
      if (!user) return;
      unwrap(await api.POST("/api/v1/users/{user_id}/password", { params: { path: { user_id: user.id } }, body: v }));
      await invalidate(qc);
      toast.success("Password reset; the user was signed out");
      form.reset();
      onClose();
    },
  });
  const e = form.formState.errors;
  return (
    <Dialog open={user !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Reset password</DialogTitle>
          <DialogDescription>Sets a new password for {user?.name ?? user?.sub} and signs them out everywhere.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
          <DialogBody className="grid gap-4">
            <FormField label="New password" error={e.new_password?.message} hint={`At least ${MIN} characters`}>
              <Input type="password" autoComplete="new-password" {...form.register("new_password")} />
            </FormField>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4" {...form.register("must_change_password")} />
              Require a password change at next sign-in
            </label>
            <FormRootError message={form.rootError} />
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button type="submit" loading={form.formState.isSubmitting}>
              Reset password
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const describe = (c: OwnedCounts) =>
  [`${c.targets} target(s)`, `${c.credentials} credential(s)`, `${c.sources} source(s)`].join(", ");

export function DeleteUserDialog({ user, others, onClose }: { user: UserOut | null; others: UserOut[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [owned, setOwned] = useState<OwnedCounts | null>(null);
  const [dest, setDest] = useState("");
  const close = () => {
    setOwned(null);
    setDest("");
    onClose();
  };
  const del = useMutation({
    mutationFn: async () => {
      if (!user) return;
      const r = await api.DELETE("/api/v1/users/{user_id}", {
        params: { path: { user_id: user.id }, query: dest ? { reassign_to: Number(dest) } : {} },
      });
      if (r.response.status === 409 && r.error && "owned" in r.error) {
        setOwned(r.error.owned);
        return;
      }
      if (r.response.status === 409) throw new Error(r.error?.detail === "last admin" ? "Cannot delete the last admin" : "Cannot delete this user");
      unwrap(r);
      await invalidate(qc);
      toast.success(`Deleted ${user.name ?? user.sub}`);
      close();
    },
    onError: (e) => toast.error(e.message),
  });
  const choices = others.filter((o) => user && o.id !== user.id && !o.disabled);
  return (
    <Dialog open={user !== null} onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Delete user</DialogTitle>
          <DialogDescription>
            Deletes {user?.name ?? user?.sub}, their API keys and their shares. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        {owned && (
          <DialogBody className="grid gap-3">
            <p role="alert" className="text-sm text-destructive">
              This user owns {describe(owned)}. Choose who takes them over.
            </p>
            <FormField label="Reassign to">
              <Select value={dest} onChange={(ev) => setDest(ev.target.value)}>
                <option value="">Select a user…</option>
                {choices.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name ?? o.sub}
                  </option>
                ))}
              </Select>
            </FormField>
          </DialogBody>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button variant="destructive" loading={del.isPending} disabled={owned !== null && !dest} onClick={() => del.mutate()}>
            {owned ? "Reassign and delete" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
