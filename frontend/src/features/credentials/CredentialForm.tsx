import { useState, type ReactNode } from "react";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { z } from "zod";
import { FormField, FormRootError } from "../../components/common/FormField";
import { SecretInput } from "../../components/common/SecretInput";
import { omitEmpty } from "../../components/common/omitEmpty";
import { useApiForm } from "../../components/common/useApiForm";
import { useExtractors } from "../sources/hooks";
import { useCreateCredential, useUpdateCredential, type CredentialIn, type CredentialKind, type CredentialOut } from "./hooks";

const KIND_HELP = {
  oauth: "OAuth refresh/access token JSON.",
  cookies: "Paste cookies (Netscape cookies.txt format or a JSON export).",
  userpass: "Username and password, as user:password.",
  token: "API or access token.",
  apprise: "Apprise URL (e.g. ntfys://topic)",
} satisfies Record<CredentialKind, string>;
const REDDIT_HELP = {
  cookies:
    "Reddit: export ALL reddit.com cookies while logged in, in Netscape or JSON form (e.g. with the Cookie-Editor or \"Get cookies.txt LOCALLY\" extension). The REST API is used; a datacenter IP may still be blocked. The OAuth app alternative needs Reddit approval.",
  oauth: 'Reddit: use JSON like {"client-id": "...", "client-secret": "...", "refresh-token": "...", "user-agent": "optional"}.',
} as const;
const KINDS = Object.keys(KIND_HELP) as CredentialKind[];

const base = {
  name: z.string().trim().min(1, "Name is required"),
  site: z.string().trim().min(1, "Site is required"),
  kind: z.enum(["oauth", "cookies", "userpass", "token", "apprise"]),
};
const createSchema = z.object({ ...base, secret: z.string().min(1, "Secret is required") });
// Same shape as create (empty secret = keep saved; omitEmpty drops it) so Fields types both forms.
const editSchema = z.object({ ...base, secret: z.string() });

function Fields({
  form,
  saved,
}: {
  form: ReturnType<typeof useApiForm<typeof createSchema>>;
  saved: boolean;
}) {
  const e = form.formState.errors;
  const kind = form.watch("kind");
  const { data: extractors } = useExtractors();
  const site = form.watch("site").trim().toLowerCase();
  const redditHelp = site === "reddit" && (kind === "cookies" || kind === "oauth") ? REDDIT_HELP[kind] : "";
  const base = saved && kind === "cookies" ? `${KIND_HELP[kind]} Saved — enter a new value to replace.` : KIND_HELP[kind];
  const hint = redditHelp ? `${base} ${redditHelp}` : base;
  return (
    <>
      <DialogBody className="grid gap-4">
      <FormField label="Name" error={e.name?.message}>
        <Input {...form.register("name")} />
      </FormField>
      <FormField label="Site" error={e.site?.message} hint="gallery-dl site name, e.g. reddit (a host like reddit.com is accepted)">
        <Input list="credential-sites" {...form.register("site")} />
      </FormField>
      <datalist id="credential-sites">
        {(extractors?.items ?? []).map((x) => (
          <option key={x.category} value={x.category} />
        ))}
      </datalist>
      <FormField label="Kind" error={e.kind?.message}>
        <Select {...form.register("kind")}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField label="Secret" error={e.secret?.message} hint={hint}>
        {kind === "cookies" ? (
          <Textarea rows={6} autoComplete="off" spellCheck={false} className="font-mono" {...form.register("secret")} />
        ) : (
          <SecretInput saved={saved} {...form.register("secret")} />
        )}
      </FormField>
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
    </>
  );
}

function CreateFields({ onDone }: { onDone: () => void }) {
  const create = useCreateCredential();
  const form = useApiForm(createSchema, {
    defaultValues: { name: "", site: "", kind: "token", secret: "" },
    onSubmit: async (v) => {
      await create.mutateAsync({ ...v, visibility: "private" } satisfies CredentialIn);
      onDone();
    },
  });
  return (
    <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
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
    <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <Fields form={form} saved={cred.has_secret} />
    </form>
  );
}

export function CredentialForm({ credential, trigger }: { credential?: CredentialOut; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const done = () => setOpen(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{credential ? `Edit ${credential.name}` : "Add credential"}</DialogTitle>
          <DialogDescription>Credential settings. Secrets are write-only.</DialogDescription>
        </DialogHeader>
        {credential ? <EditFields cred={credential} onDone={done} /> : <CreateFields onDone={done} />}
      </DialogContent>
    </Dialog>
  );
}
