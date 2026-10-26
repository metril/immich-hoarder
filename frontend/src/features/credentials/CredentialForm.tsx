import { useState, type ReactNode } from "react";
import { Dialog } from "radix-ui";
import { z } from "zod";
import { FormField, FormRootError, inputClass } from "../../components/common/FormField";
import { SecretInput } from "../../components/common/SecretInput";
import { omitEmpty } from "../../components/common/omitEmpty";
import { useApiForm } from "../../components/common/useApiForm";
import { useCreateCredential, useUpdateCredential, type CredentialKind, type CredentialOut } from "./hooks";

const KIND_HELP = {
  oauth: "OAuth refresh/access token JSON.",
  cookies: "Paste cookies (Netscape cookies.txt format or a JSON export).",
  userpass: "Username and password, as user:password.",
  token: "API or access token.",
  apprise: "Apprise URL (e.g. ntfys://topic)",
} satisfies Record<CredentialKind, string>;
const KINDS = Object.keys(KIND_HELP) as CredentialKind[];

const base = {
  name: z.string().trim().min(1, "Name is required"),
  site: z.string().trim().min(1, "Site is required"),
  kind: z.enum(["oauth", "cookies", "userpass", "token", "apprise"]),
};
const createSchema = z.object({ ...base, secret: z.string().min(1, "Secret is required") });
const editSchema = z.object({ ...base, secret: z.string().optional() });

function Fields({
  form,
  saved,
}: {
  form: ReturnType<typeof useApiForm<typeof createSchema>>;
  saved: boolean;
}) {
  const e = form.formState.errors;
  const kind = form.watch("kind");
  const hint = saved && kind === "cookies" ? `${KIND_HELP[kind]} Saved — enter a new value to replace.` : KIND_HELP[kind];
  return (
    <>
      <FormField label="Name" error={e.name?.message}>
        <input className={inputClass} {...form.register("name")} />
      </FormField>
      <FormField label="Site" error={e.site?.message}>
        <input className={inputClass} {...form.register("site")} />
      </FormField>
      <FormField label="Kind" error={e.kind?.message}>
        <select className={inputClass} {...form.register("kind")}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </FormField>
      <FormField label="Secret" error={e.secret?.message} hint={hint}>
        {kind === "cookies" ? (
          <textarea rows={6} autoComplete="off" spellCheck={false} className={`${inputClass} h-auto py-2 font-mono`} {...form.register("secret")} />
        ) : (
          <SecretInput saved={saved} {...form.register("secret")} />
        )}
      </FormField>
      <FormRootError message={form.rootError} />
      <div className="flex justify-end gap-2">
        <Dialog.Close type="button" className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
          Cancel
        </Dialog.Close>
        <button type="submit" disabled={form.formState.isSubmitting} className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50">
          Save
        </button>
      </div>
    </>
  );
}

function CreateFields({ onDone }: { onDone: () => void }) {
  const create = useCreateCredential();
  const form = useApiForm(createSchema, {
    defaultValues: { name: "", site: "", kind: "token", secret: "" },
    onSubmit: async (v) => {
      await create.mutateAsync(v as never);
      onDone();
    },
  });
  return (
    <form onSubmit={form.submit} className="mt-3 grid gap-3" noValidate>
      <Fields form={form} saved={false} />
    </form>
  );
}

function EditFields({ cred, onDone }: { cred: CredentialOut; onDone: () => void }) {
  const update = useUpdateCredential(cred.id);
  const form = useApiForm(editSchema, {
    defaultValues: { name: cred.name, site: cred.site, kind: cred.kind, secret: "" },
    onSubmit: async (v) => {
      await update.mutateAsync(omitEmpty(v, ["secret"]));
      onDone();
    },
  });
  return (
    <form onSubmit={form.submit} className="mt-3 grid gap-3" noValidate>
      <Fields form={form as never} saved={cred.has_secret} />
    </form>
  );
}

export function CredentialForm({ credential, trigger }: { credential?: CredentialOut; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const done = () => setOpen(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">{credential ? `Edit ${credential.name}` : "Add credential"}</Dialog.Title>
          <Dialog.Description className="sr-only">Credential settings. Secrets are write-only.</Dialog.Description>
          {credential ? <EditFields cred={credential} onDone={done} /> : <CreateFields onDone={done} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
