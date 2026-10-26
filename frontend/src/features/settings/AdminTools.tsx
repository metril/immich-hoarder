import { useState } from "react";
import { toast } from "sonner";
import { ApiError } from "../../api/errors";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { RelativeTime } from "../../components/common/RelativeTime";
import { useMediaQuery } from "../../components/common/useMediaQuery";
import { fmtBytes } from "../sources/schema";
import { downloadExport, importYaml, useBackup, useBackups, usePrune, type ImportResult } from "./hooks";

const MAX_IMPORT = 5 * 1024 * 1024;
const btn = "rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50";

function Backups() {
  const list = useBackups();
  const backup = useBackup();
  const narrow = useMediaQuery("(max-width: 767px)");
  const run = () =>
    backup.mutate(undefined, {
      onSuccess: (r) => toast.success(`Backup created: ${r.file}`),
      onError: (e) =>
        toast.error(
          e instanceof ApiError && e.status === 409
            ? "Backups are not supported for this database"
            : e instanceof ApiError && e.status === 507
              ? "Backup failed: disk error or no space left"
              : e.message,
        ),
    });
  return (
    <section aria-labelledby="h-backups" className="grid gap-2">
      <div className="flex items-center justify-between">
        <h2 id="h-backups" className="text-base font-semibold">Backups</h2>
        <button type="button" className={btn} disabled={backup.isPending} onClick={run}>Back up now</button>
      </div>
      {list.isError ? (
        <p role="alert" className="text-sm text-destructive">{list.error.message}</p>
      ) : (list.data?.items.length ?? 0) === 0 ? (
        <p className="text-sm text-muted-foreground">{list.isPending ? "Loading…" : "No backups yet."}</p>
      ) : narrow ? (
        <ul className="grid gap-2">
          {list.data?.items.map((b) => (
            <li key={b.file} className="grid gap-0.5 rounded-md border p-3 text-sm">
              <span className="break-all font-mono">{b.file}</span>
              <span className="text-xs text-muted-foreground">
                <RelativeTime iso={b.mtime} /> · {fmtBytes(b.size)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1 font-medium">File</th>
              <th className="py-1 font-medium">Created</th>
              <th className="py-1 text-right font-medium">Size</th>
            </tr>
          </thead>
          <tbody>
            {list.data?.items.map((b) => (
              <tr key={b.file} className="border-t">
                <td className="py-1 font-mono">{b.file}</td>
                <td className="py-1"><RelativeTime iso={b.mtime} /></td>
                <td className="py-1 text-right">{fmtBytes(b.size)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Prune() {
  const prune = usePrune();
  return (
    <section aria-labelledby="h-prune" className="grid gap-2">
      <h2 id="h-prune" className="text-base font-semibold">Maintenance</h2>
      <p className="text-sm text-muted-foreground">Delete finished jobs past the retention window and unused ephemeral sources.</p>
      <div>
        <ConfirmDialog
          title="Prune now?"
          body="Old jobs and ephemeral sources will be permanently deleted."
          confirmLabel="Prune"
          destructive
          onConfirm={async () => {
            const r = await prune.mutateAsync();
            toast.success(`Pruned ${r.jobs} jobs, ${r.ephemeral_sources} ephemeral sources`);
          }}
          trigger={<button type="button" className={btn}>Prune now</button>}
        />
      </div>
    </section>
  );
}

function Export() {
  const [secrets, setSecrets] = useState<"omit" | "encrypted">("omit");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      await downloadExport(secrets);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-labelledby="h-export" className="grid gap-2">
      <h2 id="h-export" className="text-base font-semibold">Export configuration</h2>
      <div role="radiogroup" aria-label="Secrets" className="grid gap-1 text-sm">
        <label className="flex items-center gap-2">
          <input type="radio" name="secrets" checked={secrets === "omit"} onChange={() => setSecrets("omit")} />
          Omit secrets
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="secrets" checked={secrets === "encrypted"} onChange={() => setSecrets("encrypted")} />
          Encrypted secrets (restorable only with the same server key)
        </label>
      </div>
      <div>
        <button type="button" className={btn} disabled={busy} onClick={() => void go()}>Download</button>
      </div>
    </section>
  );
}

function Import() {
  const [text, setText] = useState<string>();
  const [result, setResult] = useState<ImportResult>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const pick = async (file: File | undefined) => {
    setResult(undefined);
    setText(undefined);
    setError(undefined);
    if (!file) return;
    if (file.size > MAX_IMPORT) return setError("File is larger than 5 MB");
    setBusy(true);
    try {
      const t = await file.text();
      setText(t);
      setResult(await importYaml(t, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import check failed");
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (text === undefined) return;
    setBusy(true);
    try {
      const r = await importYaml(text, false);
      setResult(r);
      if (r.errors.length === 0) {
        toast.success("Import applied");
        setText(undefined);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };
  const sum = (m: Record<string, number>) => Object.entries(m).map(([k, v]) => `${v} ${k}`).join(", ") || "none";
  return (
    <section aria-labelledby="h-import" className="grid gap-2">
      <h2 id="h-import" className="text-base font-semibold">Import configuration</h2>
      <label className="grid gap-1 text-sm">
        <span>Config file</span>
        <input type="file" accept=".yaml,.yml" disabled={busy} onChange={(e) => void pick(e.target.files?.[0])} className="text-sm" />
      </label>
      <p className="text-xs text-muted-foreground">YAML, up to 5 MB. A dry run is checked first; nothing changes until you apply.</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {result && (
        <div className="grid gap-1 rounded-md border p-3 text-sm" aria-live="polite">
          <p className="font-medium">{result.applied ? "Applied" : "Dry run"}</p>
          <p>Created: {sum(result.created)}</p>
          <p>Skipped: {sum(result.skipped)}</p>
          {result.errors.length > 0 && (
            <ul className="list-disc pl-5 text-destructive">
              {result.errors.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          )}
        </div>
      )}
      {result && !result.applied && text !== undefined && (
        <div>
          <button type="button" className={btn} disabled={busy || result.errors.length > 0} onClick={() => void apply()}>Apply import</button>
        </div>
      )}
    </section>
  );
}

export function AdminTools() {
  return (
    <div className="grid gap-8">
      <Backups />
      <Prune />
      <Export />
      <Import />
    </div>
  );
}
