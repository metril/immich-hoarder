import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import { useMe } from "../../api/me";
import { FormField, FormRootError } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

const schema = z.object({
  current_password: z.string().min(1, "Enter your current password"),
  new_password: z.string().min(8, "At least 8 characters"),
});

function ChangeDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const form = useApiForm(schema, {
    defaultValues: { current_password: "", new_password: "" },
    onSubmit: async (v) => {
      unwrap(await api.POST("/api/v1/auth/password", { body: v }));
      await qc.invalidateQueries({ queryKey: keys.me() });
      toast.success("Password changed");
      onOpenChange(false);
    },
  });
  const e = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Change password</DialogTitle>
          <DialogDescription>An administrator reset your password. Choose a new one.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
          <DialogBody className="grid gap-4">
            <FormField label="Current password" error={e.current_password?.message}>
              <Input type="password" autoComplete="current-password" {...form.register("current_password")} />
            </FormField>
            <FormField label="New password" error={e.new_password?.message}>
              <Input type="password" autoComplete="new-password" {...form.register("new_password")} />
            </FormField>
            <FormRootError message={form.rootError} />
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Later</Button>
            </DialogClose>
            <Button type="submit" loading={form.formState.isSubmitting}>
              Change password
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Shown while an admin-reset password is still pending. */
export function MustChangePasswordBanner() {
  const me = useMe().data;
  const [open, setOpen] = useState(false);
  if (!me?.must_change_password) return null;
  return (
    <div role="alert" className="flex items-center justify-between gap-3 bg-amber-100 px-4 py-2 text-sm text-amber-950 dark:bg-amber-950 dark:text-amber-100">
      <span>Your password was reset by an administrator. Please choose a new one.</span>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Change password
      </Button>
      <ChangeDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
