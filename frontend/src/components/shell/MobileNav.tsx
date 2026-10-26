import { useEffect, useState } from "react";
import { Menu as MenuIcon, X } from "lucide-react";
import { Sidebar } from "./Sidebar";

/** Hamburger + slide-over sheet; hidden at >= md where the sidebar is visible. */
export function MobileNav({ admin }: { admin: boolean }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open]);
  return (
    <>
      <button
        type="button"
        aria-label="Open navigation"
        onClick={() => setOpen(true)}
        className="inline-flex size-9 items-center justify-center rounded-md hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring md:hidden"
      >
        <MenuIcon className="size-5" aria-hidden />
      </button>
      {open && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} aria-hidden />
          <div role="dialog" aria-modal="true" aria-label="Navigation" className="absolute inset-y-0 left-0 w-64 bg-sidebar text-sidebar-foreground shadow-xl">
            <button
              type="button"
              aria-label="Close navigation"
              autoFocus
              onClick={() => setOpen(false)}
              className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-sidebar-ring"
            >
              <X className="size-4" aria-hidden />
            </button>
            <div className="px-6 pt-4 text-sm font-semibold">Immich Hoarder</div>
            <Sidebar admin={admin} label="Mobile" onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
