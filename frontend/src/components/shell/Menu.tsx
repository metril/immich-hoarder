import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";

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
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!root.current?.contains(t) && !panel.current?.contains(t)) setOpen(false);
    };
    const close = () => setOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  return (
    <div ref={root} className="relative">
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={open}
              onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                setPos({ top: r.bottom + 8, right: window.innerWidth - r.right });
                setOpen((o) => !o);
              }}
              className="inline-flex h-9 items-center gap-2 rounded-lg px-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-ring"
            >
              <span className="sr-only">{label}</span>
              {trigger}
            </button>
          </TooltipTrigger>
          {!open && <TooltipContent>{label}</TooltipContent>}
        </Tooltip>
      </TooltipProvider>
      {open && pos && createPortal(
        <div ref={panel} role="menu" aria-label={label} style={{ top: pos.top, right: pos.right }} className="fixed z-50 min-w-44 rounded-xl border bg-popover p-1.5 text-popover-foreground shadow-lg motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-95 motion-safe:duration-150">
          {children(() => setOpen(false))}
        </div>,
        document.body,
      )}
    </div>
  );
}

export const menuItemCls =
  "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none";
