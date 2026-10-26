import type { ComponentProps } from "react";
import { cn } from "./cn";

export const controlClass =
  "h-9 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50 aria-[invalid=true]:border-destructive";

export function Input({ className, ...p }: ComponentProps<"input">) {
  return <input className={cn(controlClass, className)} {...p} />;
}
