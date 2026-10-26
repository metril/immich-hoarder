import { createContext, useContext, useRef, useState, type ComponentProps, type ReactNode } from "react";
import { DropdownMenu } from "radix-ui";
import { cn } from "../ui/cn";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

const Ctx = createContext<{ later: (fn: () => void) => void }>({ later: (fn) => fn() });

/** Accessible dropdown (Radix: roving focus, arrows/Home/End, typeahead, portaled, collision-aware). */
export function Menu({ label, trigger, children }: { label: string; trigger: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const pending = useRef<(() => void) | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  return (
    <Ctx.Provider value={{ later: (fn) => { pending.current = fn; } }}>
      <DropdownMenu.Root open={open} onOpenChange={setOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenu.Trigger
              ref={triggerRef}
              className="inline-flex h-9 items-center gap-2 rounded-lg px-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-ring"
            >
              <span className="sr-only">{label}</span>
              {trigger}
            </DropdownMenu.Trigger>
          </TooltipTrigger>
          {!open && <TooltipContent>{label}</TooltipContent>}
        </Tooltip>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={8}
            collisionPadding={8}
            aria-label={label}
            onCloseAutoFocus={(e) => {
              // Return focus to the trigger first, then run any dialog-opening action so the dialog restores focus there.
              e.preventDefault();
              triggerRef.current?.focus();
              const fn = pending.current;
              pending.current = null;
              fn?.();
            }}
            className="z-50 min-w-44 rounded-xl border bg-popover p-1.5 text-popover-foreground shadow-lg motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-95 motion-safe:duration-150"
          >
            {children}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </Ctx.Provider>
  );
}

/** `onAction` runs after the menu has closed and focus is back on the trigger. */
export function MenuItem({ onAction, className, ...p }: Omit<ComponentProps<typeof DropdownMenu.Item>, "onSelect"> & { onAction: () => void }) {
  const { later } = useContext(Ctx);
  return <DropdownMenu.Item {...p} onSelect={() => later(onAction)} className={cn(menuItemCls, className)} />;
}

export const menuItemCls =
  "flex w-full cursor-default items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm outline-none data-[highlighted]:bg-accent";
