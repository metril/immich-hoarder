import { useEffect } from "react";
import { NAV } from "./nav";
import { modLabel } from "./shortcuts";

export function ShortcutHelp({ open, onClose, admin }: { open: boolean; onClose: () => void; admin: boolean }) {
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open, onClose]);
  if (!open) return null;
  const rows: [string, string][] = [
    [`${modLabel()} K`, "Command palette"],
    ["?", "This help"],
    ["/", "Focus search"],
    ["n", "New (on list pages)"],
    ...NAV.filter((n) => admin || !n.admin).map((n): [string, string] => [n.shortcut, `Go to ${n.label}`]),
  ];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" className="relative w-full max-w-sm rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
        <h2 className="mb-3 text-base font-semibold">Keyboard shortcuts</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {rows.map(([k, d]) => (
            <div key={k + d} className="contents">
              <dt>
                <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
              </dt>
              <dd>{d}</dd>
            </div>
          ))}
        </dl>
        <button type="button" autoFocus onClick={onClose} className="mt-4 rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
          Close
        </button>
      </div>
    </div>
  );
}
