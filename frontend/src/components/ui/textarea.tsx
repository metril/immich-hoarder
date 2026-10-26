import type { ComponentProps } from "react";
import { cn } from "./cn";
import { controlClass } from "./input";

export function Textarea({ className, ...p }: ComponentProps<"textarea">) {
  return <textarea className={cn(controlClass, "h-auto min-h-20 py-2", className)} {...p} />;
}
