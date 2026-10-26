import type { ComponentProps } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "./cn";

export const badgeVariants = cva(
  "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
  {
    variants: {
      tone: {
        neutral: "bg-muted text-foreground",
        primary: "border-primary/30 bg-primary/15 text-accent-foreground",
        success: "border-success/30 bg-success/15 text-foreground",
        warning: "border-warning/30 bg-warning/15 text-foreground",
        info: "border-info/30 bg-info/15 text-foreground",
        danger: "border-danger/30 bg-danger/15 text-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

const DOT: Record<NonNullable<VariantProps<typeof badgeVariants>["tone"]>, string> = {
  neutral: "bg-muted-foreground",
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  info: "bg-info",
  danger: "bg-danger",
};

export function Badge({
  className,
  tone,
  dot,
  children,
  ...p
}: ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { dot?: boolean }) {
  return (
    <span className={cn(badgeVariants({ tone }), className)} {...p}>
      {dot ? <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", DOT[tone ?? "neutral"])} /> : null}
      {children}
    </span>
  );
}
