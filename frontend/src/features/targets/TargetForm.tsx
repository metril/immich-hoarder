import { useState, type ReactNode } from "react";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { z } from "zod";
import { FormField, FormRootError } from "../../components/common/FormField";
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
    <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <DialogBody className="grid gap-4">
      <FormField label="Name" error={e.name?.message}>
        <Input {...form.register("name")} />
      </FormField>
      <FormField label="URL" error={e.url?.message}>
        <Input inputMode="url" {...form.register("url")} />
      </FormField>
      <FormField label="API key" error={e.api_key?.message}>
        <SecretInput saved={false} {...form.register("api_key")} />
      </FormField>
      <FormField label="Visibility" error={e.visibility?.message} hint="Change later via Share.">
        <Select {...form.register("visibility")}>
          <option value="private">Private</option>
          <option value="everyone">Everyone</option>
          <option value="restricted">Restricted</option>
        </Select>
      </FormField>
      <FormRootError message={form.rootError} />
      </DialogBody>
      <Actions busy={form.formState.isSubmitting} />
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
    <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <DialogBody className="grid gap-4">
      <FormField label="Name" error={e.name?.message}>
        <Input {...form.register("name")} />
      </FormField>
      <FormField label="URL" error={e.url?.message}>
        <Input inputMode="url" {...form.register("url")} />
      </FormField>
      <FormField label="API key" error={e.api_key?.message}>
        <SecretInput saved={target.has_api_key} {...form.register("api_key")} />
      </FormField>
      <FormRootError message={form.rootError} />
      </DialogBody>
      <Actions busy={form.formState.isSubmitting} />
    </form>
  );
}

function Actions({ busy }: { busy: boolean }) {
  return (
    <DialogFooter>
      <DialogClose asChild>
        <Button variant="outline">Cancel</Button>
      </DialogClose>
      <Button type="submit" loading={busy}>
        Save
      </Button>
    </DialogFooter>
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
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{target ? `Edit ${target.name}` : "Add target"}</DialogTitle>
          <DialogDescription>Immich target settings</DialogDescription>
        </DialogHeader>
        {target ? <EditFields target={target} onDone={done} /> : <CreateFields onDone={done} />}
      </DialogContent>
    </Dialog>
  );
}
