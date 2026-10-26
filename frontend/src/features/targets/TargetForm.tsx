import { useState, type ReactNode } from "react";
import { Dialog } from "radix-ui";
import { z } from "zod";
import { FormField, FormRootError, inputClass } from "../../components/common/FormField";
import { SecretInput } from "../../components/common/SecretInput";
import { omitEmpty } from "../../components/common/omitEmpty";
import { useApiForm } from "../../components/common/useApiForm";
import { useCreateTarget, useUpdateTarget, type TargetOut } from "./hooks";

const base = { name: z.string().trim().min(1, "Name is required"), url: z.url("Enter a valid URL") };
const createSchema = z.object({
  ...base,
  api_key: z.string().min(1, "API key is required"),
  visibility: z.enum(["private", "everyone", "restricted"]),
});
const editSchema = z.object({ ...base, api_key: z.string().optional() });

function CreateFields({ onDone }: { onDone: () => void }) {
  const create = useCreateTarget();
  const form = useApiForm(createSchema, {
    defaultValues: { name: "", url: "", api_key: "", visibility: "private" },
    onSubmit: async (v) => {
      await create.mutateAsync(v);
      onDone();
    },
  });
  const e = form.formState.errors;
  return (
    <form onSubmit={form.submit} className="mt-3 grid gap-3" noValidate>
      <FormField label="Name" error={e.name?.message}>
        <input className={inputClass} {...form.register("name")} />
      </FormField>
      <FormField label="URL" error={e.url?.message}>
        <input className={inputClass} inputMode="url" {...form.register("url")} />
      </FormField>
      <FormField label="API key" error={e.api_key?.message}>
        <SecretInput saved={false} {...form.register("api_key")} />
      </FormField>
      <FormField label="Visibility" error={e.visibility?.message} hint="Change later via Share.">
        <select className={inputClass} {...form.register("visibility")}>
          <option value="private">Private</option>
          <option value="everyone">Everyone</option>
          <option value="restricted">Restricted</option>
        </select>
      </FormField>
      <Actions root={form.rootError} busy={form.formState.isSubmitting} />
    </form>
  );
}

function EditFields({ target, onDone }: { target: TargetOut; onDone: () => void }) {
  const update = useUpdateTarget(target.id);
  const form = useApiForm(editSchema, {
    defaultValues: { name: target.name, url: target.url, api_key: "" },
    onSubmit: async (v) => {
      await update.mutateAsync(omitEmpty(v, ["api_key"]));
      onDone();
    },
  });
  const e = form.formState.errors;
  return (
    <form onSubmit={form.submit} className="mt-3 grid gap-3" noValidate>
      <FormField label="Name" error={e.name?.message}>
        <input className={inputClass} {...form.register("name")} />
      </FormField>
      <FormField label="URL" error={e.url?.message}>
        <input className={inputClass} inputMode="url" {...form.register("url")} />
      </FormField>
      <FormField label="API key" error={e.api_key?.message}>
        <SecretInput saved={target.has_api_key} {...form.register("api_key")} />
      </FormField>
      <Actions root={form.rootError} busy={form.formState.isSubmitting} />
    </form>
  );
}

function Actions({ root, busy }: { root?: string; busy: boolean }) {
  return (
    <>
      <FormRootError message={root} />
      <div className="flex justify-end gap-2">
        <Dialog.Close type="button" className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
          Cancel
        </Dialog.Close>
        <button type="submit" disabled={busy} className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50">
          Save
        </button>
      </div>
    </>
  );
}

/** Create (no `target`) or edit dialog. Fields remount on open so secrets are never retained. */
export function TargetForm({
  target,
  trigger,
  open: controlled,
  onOpenChange,
}: {
  target?: TargetOut;
  trigger: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [own, setOwn] = useState(false);
  const open = controlled ?? own;
  const setOpen = onOpenChange ?? setOwn;
  const done = () => setOpen(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">{target ? `Edit ${target.name}` : "Add target"}</Dialog.Title>
          <Dialog.Description className="sr-only">Immich target settings</Dialog.Description>
          {target ? <EditFields target={target} onDone={done} /> : <CreateFields onDone={done} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
