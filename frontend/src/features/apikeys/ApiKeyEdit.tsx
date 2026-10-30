import { useState, type ReactNode } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { isAdmin, useMe } from "../../api/me";
import { FormField, FormRootError } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { useUpdateApiKey, type ApiKeyOut } from "./hooks";
import { groupScopes, type Scope } from "./scopes";

const schema = z.object({
  name: z.string().trim().min(1, "Name is required"),
  scopes: z.array(z.custom<Scope>((v) => typeof v === "string")).min(1, "Select at least one scope"),
});

function Fields({ k, onDone }: { k: ApiKeyOut; onDone: () => void }) {
  const admin = isAdmin(useMe().data);
  const update = useUpdateApiKey(k.id);
  const form = useApiForm(schema, {
    defaultValues: { name: k.name, scopes: k.scopes as Scope[] },
    onSubmit: async (v) => {
      await update.mutateAsync({ name: v.name, scopes: v.scopes });
      onDone();
    },
  });
  const e = form.formState.errors;
  return (
    <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <DialogBody className="grid gap-5">
        <FormField label="Name" error={e.name?.message}>
          <Input {...form.register("name")} />
        </FormField>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">Scopes</legend>
          {groupScopes(admin).map(([group, scopes]) => (
            <div key={group} role="group" aria-label={group} className="flex flex-wrap gap-x-5 gap-y-2">
              <span className="w-full text-xs font-medium capitalize text-muted-foreground">{group}</span>
              {scopes.map((s) => (
                <label key={s} className="flex items-center gap-1.5 text-sm">
                  <input type="checkbox" value={s} className="size-4" {...form.register("scopes")} />
                  {s}
                </label>
              ))}
            </div>
          ))}
          {e.scopes && <p role="alert" className="text-sm text-destructive">{e.scopes.message}</p>}
        </fieldset>
        <FormRootError message={form.rootError} />
      </DialogBody>
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="outline">Cancel</Button>
        </DialogClose>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ApiKeyEdit({ k, trigger }: { k: ApiKeyOut; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit {k.name}</DialogTitle>
          <DialogDescription>Rename the key or change its scopes. Expiry cannot be changed.</DialogDescription>
        </DialogHeader>
        <Fields k={k} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}
