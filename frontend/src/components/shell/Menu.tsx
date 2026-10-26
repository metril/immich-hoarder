import { useEffect, useRef, useState, type ReactNode } from "react";

/** Minimal dropdown: click-outside and Escape close it. */
export function Menu({
  label,
  trigger,
  children,
}: {
  label: string;
  trigger: ReactNode;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-9 items-center gap-2 rounded-md px-2 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
      >
        {trigger}
      </button>
      {open && (
        <div role="menu" aria-label={label} className="absolute right-0 z-40 mt-1 min-w-40 rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export const menuItemCls =
  "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none";
