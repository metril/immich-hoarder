import { useState } from "react";
import { Dialog } from "radix-ui";
import { toast } from "sonner";

/** Shows the plaintext once. The parent clears `secret` on close, so it is dropped from state. */
export function KeyRevealDialog({ secret, onClose }: { secret: string | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret ?? "");
      setCopied(true);
    } catch {
      toast.error("Could not copy; select the key and copy it manually");
    }
  };
  return (
    <Dialog.Root
      open={secret !== null}
      onOpenChange={(o) => {
        if (!o) {
          setCopied(false);
          onClose();
        }
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">API key created</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm font-medium text-destructive">
            This key will not be shown again
          </Dialog.Description>
          <input
            readOnly
            aria-label="API key"
            value={secret ?? ""}
            onFocus={(e) => e.currentTarget.select()}
            className="mt-3 h-9 w-full rounded-md border bg-background px-3 font-mono text-xs focus-visible:outline-2 focus-visible:outline-ring"
          />
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" onClick={() => void copy()} className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
              {copied ? "Copied" : "Copy"}
            </button>
            <Dialog.Close className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring">
              Done
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
