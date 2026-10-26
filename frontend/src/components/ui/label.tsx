import type { ComponentProps } from "react";
import { cn } from "./cn";

export function Label({ className, ...p }: ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium leading-none", className)} {...p} />;
}
