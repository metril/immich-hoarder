import type { ComponentProps } from "react";
import { cn } from "./cn";
import { controlClass } from "./input";

/** Native select; styled to match Input. */
export function Select({ className, ...p }: ComponentProps<"select">) {
  return <select className={cn(controlClass, "pr-8", className)} {...p} />;
}
