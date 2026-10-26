import { useState, type ReactNode } from "react";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { z } from "zod";
import { isAdmin, useMe } from "../../api/me";
import { FormField, FormRootError } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { useCreateApiKey } from "./hooks";
import { allScopes, groupScopes, readOnlyScopes, type Scope } from "./scopes";

const today = () => new Date().toISOString().slice(0, 10); // UTC date, matches the 23:59:59Z we send

const schema = z.object({
  name: z.string().trim().min(1, "Name is required"),
  scopes: z.array(z.custom<Scope>((v) => typeof v === "string")).min(1, "Select at least one scope"),
  expires_at: z
    .string()
    .optional()
    .refine((d) => !d || d >= today(), "Expiry must be today or later"),
});

function Fields({ onKey, onDone }: { onKey: (k: string) => void; onDone: () => void }) {
  const admin = isAdmin(useMe().data);
  const create = useCreateApiKey(onKey);
  const form = useApiForm(schema, {
    defaultValues: { name: "", scopes: [], expires_at: "" },
    onSubmit: async (v) => {
      await create.mutateAsync({
        name: v.name,
        scopes: v.scopes,
        ...(v.expires_at ? { expires_at: `${v.expires_at}T23:59:59Z` } : {}),
      });
      onDone();
    },
  });
  const e = form.formState.errors;
  const setScopes = (s: Scope[]) => form.setValue("scopes", s, { shouldValidate: form.formState.isSubmitted });
  return (
    <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <DialogBody className="grid gap-5">
      <FormField label="Name" error={e.name?.message}>
        <Input {...form.register("name")} />
      </FormField>
      <fieldset className="grid gap-2" aria-describedby={e.scopes ? "scopes-err" : undefined}>
        <legend className="mb-1 text-sm font-medium">Scopes</legend>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setScopes(readOnlyScopes())}>Read-only</Button>
          <Button size="sm" variant="outline" onClick={() => setScopes(allScopes(admin))}>All</Button>
        </div>
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
        {e.scopes && <p id="scopes-err" role="alert" className="text-sm text-destructive">{e.scopes.message}</p>}
      </fieldset>
      <FormField label="Expires (optional, UTC)" error={e.expires_at?.message}>
        <Input type="date" min={today()} {...form.register("expires_at")} />
      </FormField>
      <FormRootError message={form.rootError} />
      </DialogBody>
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="outline">Cancel</Button>
        </DialogClose>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Create key
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ApiKeyForm({ trigger, onKey }: { trigger: ReactNode; onKey: (plaintext: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New API key</DialogTitle>
          <DialogDescription>Choose a name, scopes and optional expiry.</DialogDescription>
        </DialogHeader>
        <Fields onKey={onKey} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}
