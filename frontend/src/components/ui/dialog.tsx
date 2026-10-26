import type { ComponentProps } from "react";
import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "./cn";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

/** Blurred overlay; body scrolls within max-h-[85dvh]; put DialogFooter last to keep it pinned. */
export function DialogContent({ className, children, ...p }: ComponentProps<typeof D.Content>) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:fade-in-0 motion-safe:data-[state=closed]:animate-out motion-safe:data-[state=closed]:fade-out-0 motion-safe:duration-150" />
      <D.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 flex max-h-[85dvh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-xl motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:fade-in-0 motion-safe:data-[state=open]:zoom-in-95 motion-safe:duration-150",
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
export function DialogHeader({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-1.5 p-5 pr-10 md:p-6 md:pr-12", className)} {...p} />;
}
export function DialogBody({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("min-h-0 flex-1 overflow-y-auto px-5 pb-5 md:px-6", className)} {...p} />;
}
export function DialogFooter({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("flex flex-wrap justify-end gap-2 border-t p-4 md:px-6", className)} {...p} />;
}
export function DialogTitle({ className, ...p }: ComponentProps<typeof D.Title>) {
  return <D.Title className={cn("font-display text-lg font-semibold", className)} {...p} />;
}
export function DialogDescription({ className, ...p }: ComponentProps<typeof D.Description>) {
  return <D.Description className={cn("text-sm text-muted-foreground", className)} {...p} />;
}
