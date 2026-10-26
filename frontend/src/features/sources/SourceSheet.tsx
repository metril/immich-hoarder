import { Suspense, lazy, useState } from "react";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../../components/ui/sheet";
import { Truncate } from "../../components/ui/truncate";
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
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-2xl">
        <SheetHeader>
          <SheetTitle className="min-w-0"><Truncate>{title}</Truncate></SheetTitle>
          <SheetDescription className="sr-only">Source settings</SheetDescription>
        </SheetHeader>
        {edit !== undefined && !source ? (
          <SheetBody>
            {fetched.isError ? (
              <p role="alert" className="text-destructive">{fetched.error.message}</p>
            ) : (
              <p role="status">Loading…</p>
            )}
          </SheetBody>
        ) : (
          <EditorWithPreview source={source} onClose={onClose} />
        )}
      </SheetContent>
    </Sheet>
  );
}

/** Mounted only while the sheet is open, so the draft resets on close. */
function EditorWithPreview({ source, onClose }: { source?: SourceOut; onClose: () => void }) {
  const [draft, setDraft] = useState<SourceIn | null>(null);
  return (
    <Suspense fallback={<SheetBody><p role="status">Loading editor…</p></SheetBody>}>
      <SourceForm
        initial={source}
        onSaved={onClose}
        onCancel={onClose}
        onDraft={setDraft}
        extra={
          <section aria-label="Dry run" className="grid gap-4 rounded-xl border bg-card p-5">
            <h3 className="font-display text-base font-semibold">Dry run (unsaved values)</h3>
            {draft ? <PreviewPanel draft={draft} /> : <p className="text-sm text-muted-foreground">Fix the form errors to dry-run this draft.</p>}
          </section>
        }
      />
    </Suspense>
  );
}
