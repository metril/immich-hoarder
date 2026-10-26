import { Suspense, lazy, useState } from "react";
import { Dialog } from "radix-ui";
import { PreviewPanel } from "./PreviewPanel";
import { useSource, type SourceIn, type SourceOut } from "./hooks";

// R3: the editor (zod, react-hook-form, cronstrue) is its own lazy chunk.
const SourceForm = lazy(() => import("./SourceForm").then((m) => ({ default: m.SourceForm })));

/** Right-side sheet for ?new=1 / ?edit=<id>. `rows` lets an already-loaded source skip a fetch. */
export function SourceSheet({ edit, isNew, rows, onClose }: { edit?: number; isNew?: boolean; rows: SourceOut[]; onClose: () => void }) {
  const open = isNew === true || edit !== undefined;
  const cached = edit !== undefined ? rows.find((s) => s.id === edit) : undefined;
  const fetched = useSource(edit, open && edit !== undefined && !cached);
  const source = cached ?? fetched.data;
  const title = edit !== undefined ? `Edit ${source?.name ?? `source #${edit}`}` : "New source";
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl overflow-auto border-l bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="sr-only">Source settings</Dialog.Description>
          <div className="mt-4">
            {edit !== undefined && !source ? (
              fetched.isError ? (
                <p role="alert" className="text-destructive">{fetched.error.message}</p>
              ) : (
                <p role="status">Loading…</p>
              )
            ) : (
              <EditorWithPreview source={source} onClose={onClose} />
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Mounted only while the sheet is open, so the draft resets on close. */
function EditorWithPreview({ source, onClose }: { source?: SourceOut; onClose: () => void }) {
  const [draft, setDraft] = useState<SourceIn | null>(null);
  return (
    <>
      <Suspense fallback={<p role="status">Loading editor…</p>}>
        <SourceForm initial={source} onSaved={onClose} onCancel={onClose} onDraft={setDraft} />
      </Suspense>
      <section aria-label="Dry run" className="mt-6 border-t pt-4">
        <h3 className="mb-2 text-sm font-medium">Dry run (unsaved values)</h3>
        {draft ? <PreviewPanel draft={draft} /> : <p className="text-sm text-muted-foreground">Fix the form errors to dry-run this draft.</p>}
      </section>
    </>
  );
}
