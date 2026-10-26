import { useRef, useState } from "react";
import { Dialog } from "radix-ui";
import { toast } from "sonner";
import type { components } from "../../api/schema";
import { useTestTarget } from "./hooks";

export function TestResult({ r }: { r: components["schemas"]["TargetTestOut"] }) {
  if (r.ok) {
    return (
      <p role="status" className="font-medium text-green-700 dark:text-green-400">
        Connected · Immich v{r.version ?? "?"}
      </p>
    );
  }
  return (
    <div role="status" className="space-y-2 text-destructive">
      <p>{r.error ?? "Connection failed"}</p>
      {r.missing_permissions.length > 0 && (
        <>
          <p className="text-sm">Missing permissions:</p>
          <ul className="list-disc pl-5 text-sm">
            {r.missing_permissions.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function TargetTestButton({ id, name }: { id: number; name: string }) {
  const [open, setOpen] = useState(false);
  const test = useTestTarget();
  const btnRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <button
        ref={btnRef}
        type="button"
        aria-label={`Test ${name}`}
        disabled={test.isPending}
        onClick={() => {
          test.mutate(id, {
            onSuccess: () => setOpen(true),
            onError: (e) => toast.error(e.message),
          });
        }}
        className="rounded-md border px-2 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
      >
        {test.isPending ? "Testing…" : "Test"}
      </button>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            btnRef.current?.focus();
          }}
          className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">Test {name}</Dialog.Title>
          <Dialog.Description className="sr-only">Connection test result</Dialog.Description>
          <div className="mt-3">{test.data && <TestResult r={test.data} />}</div>
          <div className="mt-4 flex justify-end">
            <Dialog.Close className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
              Close
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
