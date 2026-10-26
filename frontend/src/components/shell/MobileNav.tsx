import { Dialog } from "radix-ui";
import { Menu as MenuIcon, X } from "lucide-react";
import type { MeOut } from "../../api/me";
import { useEffect } from "react";
import { useMediaQuery } from "../common/useMediaQuery";
import { Sidebar } from "./Sidebar";

/** Hamburger + slide-over sheet (Radix Dialog: focus trap, Escape, focus restore); hidden at >= md. */
export function MobileNav({ admin, me, open, onOpenChange }: { admin: boolean; me: MeOut; open: boolean; onOpenChange: (o: boolean) => void }) {
  const wide = useMediaQuery("(min-width:768px)");
  useEffect(() => {
    if (wide && open) onOpenChange(false);
  }, [wide, open, onOpenChange]);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger
        aria-label="Open navigation"
        className="inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring md:hidden"
      >
        <MenuIcon className="size-5" aria-hidden />
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150 md:hidden" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] border-r bg-sidebar pb-[env(safe-area-inset-bottom)] text-sidebar-foreground shadow-xl motion-safe:animate-in motion-safe:slide-in-from-left motion-safe:duration-150 md:hidden"
        >
          <Dialog.Title className="sr-only">Navigation</Dialog.Title>
          <Dialog.Close
            aria-label="Close navigation"
            className="absolute right-3 top-4 inline-flex size-8 items-center justify-center rounded-lg hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-sidebar-ring"
          >
            <X className="size-4" aria-hidden />
          </Dialog.Close>
          <Sidebar admin={admin} me={me} label="Mobile" onNavigate={() => onOpenChange(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
