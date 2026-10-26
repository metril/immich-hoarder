import type { ComponentProps } from "react";
import { cn } from "./cn";

export function Skeleton({ className, ...p }: ComponentProps<"div">) {
  return <div aria-hidden className={cn("rounded-md bg-muted motion-safe:animate-pulse", className)} {...p} />;
}
