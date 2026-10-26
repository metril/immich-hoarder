import type { ComponentProps } from "react";
import { cn } from "./cn";

/** Single-line ellipsis that exposes the full text via title. */
export function Truncate({ className, children, title, ...p }: ComponentProps<"span">) {
  return (
    <span
      title={title ?? (typeof children === "string" || typeof children === "number" ? String(children) : undefined)}
      className={cn("block min-w-0 truncate", className)}
      {...p}
    >
      {children}
    </span>
  );
}
