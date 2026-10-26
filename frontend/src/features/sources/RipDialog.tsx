import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "../../components/ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select } from "../../components/ui/select";
import { jobNav, useRip, type RipIn } from "./hooks";
import { useUsableCredentials, useUsableTargets } from "./pickers";

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
  const field = (id: string, label: string, key: string, el: (p: { id: string; "aria-invalid"?: true; "aria-describedby"?: string }) => React.ReactNode) => (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      {el({ id, "aria-invalid": fe[key] ? true : undefined, "aria-describedby": fe[key] ? `${id}-err` : undefined })}
      {fe[key] && <p id={`${id}-err`} role="alert" className="text-sm text-destructive">{fe[key]}</p>}
    </div>
  );
  return (
    <form
      className="flex min-h-0 flex-1 flex-col"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        const body: RipIn = {
          url: url.trim(), target_id: Number(target), credential_id: cred ? Number(cred) : null, album_template: album,
          name: "", visibility: "private", enabled: true, ephemeral: false, allow_animated: false, backfill_mode: "full",
          filters: { phash_distance: 3 }, gdl_options: {}, notify: { credential_ids: [], on: ["failure"] },
        };
        rip.mutate(
          body,
          {
            onSuccess: (job) => {
              onDone();
              void navigate(jobNav(job.id));
            },
          },
        );
      }}
    >
      <DialogBody className="grid gap-4">
        {field("rip-url", "URL", "url", (p) => <Input {...p} inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} />)}
        {field(
          "rip-target",
          "Target",
          "target_id",
          (p) => <Select {...p} value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Select a target…</option>
            {targets.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </Select>,
        )}
        {field(
          "rip-cred",
          "Credential (optional)",
          "credential_id",
          (p) => <Select {...p} value={cred} onChange={(e) => setCred(e.target.value)}>
            <option value="">None</option>
            {creds.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>,
        )}
        {field("rip-album", "Album template (optional)", "album_template", (p) => <Input {...p} className="font-mono" value={album} onChange={(e) => setAlbum(e.target.value)} />)}
        <p className="text-xs text-muted-foreground">Ad-hoc rips are always private to you.</p>
        {rip.isError && !Object.keys(fe).length && <p role="alert" className="text-sm text-destructive">{rip.error.message}</p>}
      </DialogBody>
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="outline">Cancel</Button>
        </DialogClose>
        <Button type="submit" loading={rip.isPending} disabled={!url.trim() || !target}>
          Start rip
        </Button>
      </DialogFooter>
    </form>
  );
}

/** Controlled dialog (opened from the page header and the command palette). */
export function RipDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Ad-hoc rip</DialogTitle>
          <DialogDescription>Download a URL once, without saving a source.</DialogDescription>
        </DialogHeader>
        <Body onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
