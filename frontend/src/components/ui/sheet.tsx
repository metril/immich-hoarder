import type { ComponentProps } from "react";
import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "./cn";

export { Dialog as Sheet, DialogTrigger as SheetTrigger, DialogClose as SheetClose } from "./dialog";
export {
  DialogHeader as SheetHeader,
  DialogBody as SheetBody,
  DialogFooter as SheetFooter,
  DialogTitle as SheetTitle,
  DialogDescription as SheetDescription,
} from "./dialog";

/** Right-side panel; full height, body scrolls, footer pinned. */
export function SheetContent({ className, children, ...p }: ComponentProps<typeof D.Content>) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:fade-in-0 motion-safe:data-[state=closed]:animate-out motion-safe:data-[state=closed]:fade-out-0 motion-safe:duration-150" />
      <D.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex h-dvh w-full max-w-md flex-col border-l bg-popover text-popover-foreground shadow-xl motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:slide-in-from-right motion-safe:data-[state=closed]:animate-out motion-safe:data-[state=closed]:slide-out-to-right motion-safe:duration-150",
          className,
        )}
        {...p}
      >
        {children}
        <D.Close
          aria-label="Close"
          className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          <X className="size-4" aria-hidden />
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}
