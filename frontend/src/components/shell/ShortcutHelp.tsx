import { Dialog } from "radix-ui";
import { Button } from "../ui/button";
import { NAV } from "./nav";
import { modLabel } from "./shortcuts";

export function ShortcutHelp({ open, onClose, admin }: { open: boolean; onClose: () => void; admin: boolean }) {
  const rows: [string, string][] = [
    [`${modLabel()} K`, "Command palette"],
    ["?", "This help"],
    ["/", "Focus search"],
    ["n", "New (on list pages)"],
    ...NAV.filter((n) => admin || !n.admin).map((n): [string, string] => [n.shortcut, `Go to ${n.label}`]),
  ];
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-2xl border bg-popover p-6 text-popover-foreground shadow-xl motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-95 motion-safe:duration-150"
        >
          <Dialog.Title className="mb-4 font-display text-lg font-semibold">Keyboard shortcuts</Dialog.Title>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {rows.map(([k, d]) => (
              <div key={k + d} className="contents">
                <dt>
                  <kbd className="rounded-md border bg-muted px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
                </dt>
                <dd>{d}</dd>
              </div>
            ))}
          </dl>
          <Dialog.Close asChild>
            <Button variant="outline" className="mt-5">
              Close
            </Button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
