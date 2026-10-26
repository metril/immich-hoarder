import { useState, type ReactNode } from "react";
import { Dialog } from "radix-ui";
import { toast } from "sonner";

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  destructive,
  onConfirm,
  trigger,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => Promise<void> | void;
  trigger: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">{body}</Dialog.Description>
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
              Cancel
            </Dialog.Close>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                void (async () => {
                  try {
                    await onConfirm();
                    setOpen(false);
                  } catch (e) {
                    toast.error(e instanceof Error ? e.message : "Action failed");
                  } finally {
                    setBusy(false);
                  }
                })();
              }}
              className={`rounded-md px-3 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50 ${destructive ? "bg-destructive text-destructive-foreground" : "bg-primary text-primary-foreground"}`}
            >
              {confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
