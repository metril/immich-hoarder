import type { ComponentProps } from "react";
import { Switch as S } from "radix-ui";
import { cn } from "./cn";

export function Switch({ className, ...p }: ComponentProps<typeof S.Root>) {
  return (
    <S.Root
      className={cn(
        "peer inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border bg-muted transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50 data-[state=checked]:border-transparent data-[state=checked]:bg-primary",
        className,
      )}
      {...p}
    >
      <S.Thumb className="block size-4 translate-x-0.5 rounded-full bg-white shadow-sm ring-1 ring-black/10 transition-transform data-[state=checked]:translate-x-[18px]" />
    </S.Root>
  );
}
