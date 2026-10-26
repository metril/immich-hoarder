import { useState } from "react";
import { Dialog } from "radix-ui";
import { Menu as MenuIcon, X } from "lucide-react";
import { Sidebar } from "./Sidebar";

/** Hamburger + slide-over sheet (Radix Dialog: focus trap, Escape, focus restore); hidden at >= md. */
export function MobileNav({ admin }: { admin: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger
        aria-label="Open navigation"
        className="inline-flex size-9 items-center justify-center rounded-md hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring md:hidden"
      >
        <MenuIcon className="size-5" aria-hidden />
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 md:hidden" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 w-64 bg-sidebar text-sidebar-foreground shadow-xl md:hidden"
        >
          <Dialog.Title className="px-6 pt-4 text-sm font-semibold">Navigation</Dialog.Title>
          <Dialog.Close
            aria-label="Close navigation"
            className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-sidebar-ring"
          >
            <X className="size-4" aria-hidden />
          </Dialog.Close>
          <Sidebar admin={admin} label="Mobile" onNavigate={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
