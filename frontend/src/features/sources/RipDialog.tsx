import { useState } from "react";
import { Dialog } from "radix-ui";
import { useNavigate } from "@tanstack/react-router";
import { inputClass } from "../../components/common/FormField";
import { jobNav, useRip, type RipIn } from "./hooks";
import { useUsableCredentials, useUsableTargets } from "./pickers";

const btn = "rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring";

function Body({ onDone }: { onDone: () => void }) {
  const [url, setUrl] = useState("");
  const [target, setTarget] = useState("");
  const [cred, setCred] = useState("");
  const [album, setAlbum] = useState("");
  const targets = useUsableTargets();
  const creds = useUsableCredentials().filter((c) => c.kind !== "apprise");
  const rip = useRip();
  const navigate = useNavigate();
  const fe = (rip.error as { fieldErrors?: Record<string, string> } | null)?.fieldErrors ?? {};
  const field = (id: string, label: string, key: string, el: React.ReactNode) => (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      {el}
      {fe[key] && <p role="alert" className="text-sm text-destructive">{fe[key]}</p>}
    </div>
  );
  return (
    <form
      className="mt-3 grid gap-3"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        rip.mutate(
          { url: url.trim(), target_id: Number(target), credential_id: cred ? Number(cred) : null, album_template: album, visibility: "private" } as RipIn,
          {
            onSuccess: (job) => {
              onDone();
              void navigate(jobNav(job.id));
            },
          },
        );
      }}
    >
      {field("rip-url", "URL", "url", <input id="rip-url" className={inputClass} inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} />)}
      {field(
        "rip-target",
        "Target",
        "target_id",
        <select id="rip-target" className={inputClass} value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Select a target…</option>
          {targets.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>,
      )}
      {field(
        "rip-cred",
        "Credential (optional)",
        "credential_id",
        <select id="rip-cred" className={inputClass} value={cred} onChange={(e) => setCred(e.target.value)}>
          <option value="">None</option>
          {creds.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>,
      )}
      {field("rip-album", "Album template (optional)", "album_template", <input id="rip-album" className={inputClass} value={album} onChange={(e) => setAlbum(e.target.value)} />)}
      <p className="text-xs text-muted-foreground">Ad-hoc rips are always private to you.</p>
      {rip.isError && !Object.keys(fe).length && <p role="alert" className="text-sm text-destructive">{rip.error.message}</p>}
      <div className="flex justify-end gap-2">
        <Dialog.Close type="button" className={btn}>Cancel</Dialog.Close>
        <button
          type="submit"
          disabled={rip.isPending || !url.trim() || !target}
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
        >
          Start rip
        </button>
      </div>
    </form>
  );
}

/** Controlled dialog (opened from the page header and the command palette). */
export function RipDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">Ad-hoc rip</Dialog.Title>
          <Dialog.Description className="text-sm text-muted-foreground">Download a URL once, without saving a source.</Dialog.Description>
          <Body onDone={() => onOpenChange(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
