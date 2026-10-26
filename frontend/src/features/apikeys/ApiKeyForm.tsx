import { useState, type ReactNode } from "react";
import { Dialog } from "radix-ui";
import { z } from "zod";
import { isAdmin, useMe } from "../../api/me";
import { FormField, FormRootError, inputClass } from "../../components/common/FormField";
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

const btn = "rounded-md border px-2 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring";

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
    <form onSubmit={form.submit} className="mt-3 grid gap-3" noValidate>
      <FormField label="Name" error={e.name?.message}>
        <input className={inputClass} {...form.register("name")} />
      </FormField>
      <fieldset className="grid gap-2" aria-describedby={e.scopes ? "scopes-err" : undefined}>
        <legend className="mb-1 text-sm font-medium">Scopes</legend>
        <div className="flex gap-2">
          <button type="button" className={btn} onClick={() => setScopes(readOnlyScopes())}>Read-only</button>
          <button type="button" className={btn} onClick={() => setScopes(allScopes(admin))}>All</button>
        </div>
        {groupScopes(admin).map(([group, scopes]) => (
          <div key={group} role="group" aria-label={group} className="flex flex-wrap gap-x-4 gap-y-1">
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
        <input type="date" min={today()} className={inputClass} {...form.register("expires_at")} />
      </FormField>
      <FormRootError message={form.rootError} />
      <div className="flex justify-end gap-2">
        <Dialog.Close type="button" className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">Cancel</Dialog.Close>
        <button type="submit" disabled={form.formState.isSubmitting} className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50">
          Create key
        </button>
      </div>
    </form>
  );
}

export function ApiKeyForm({ trigger, onKey }: { trigger: ReactNode; onKey: (plaintext: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">New API key</Dialog.Title>
          <Dialog.Description className="sr-only">Choose a name, scopes and optional expiry.</Dialog.Description>
          <Fields onKey={onKey} onDone={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
