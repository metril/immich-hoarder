import type { ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Card } from "./card";
import { cn } from "./cn";

const iconTone = cva("grid size-9 shrink-0 place-items-center rounded-lg [&_svg]:size-4", {
  variants: {
    tone: {
      neutral: "bg-muted text-muted-foreground",
      primary: "bg-primary/15 text-primary",
      success: "bg-success/15 text-success",
      warning: "bg-warning/15 text-warning",
      info: "bg-info/15 text-info",
      danger: "bg-danger/15 text-danger",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function StatTile({
  label,
  value,
  icon,
  tone,
  className,
}: { label: string; value: ReactNode; icon?: ReactNode; className?: string } & VariantProps<typeof iconTone>) {
  return (
    <Card className={cn("flex items-center gap-4 p-5", className)}>
      {icon ? (
        <span aria-hidden className={iconTone({ tone })}>
          {icon}
        </span>
      ) : null}
      <div className="min-w-0">
        <div className="font-display text-2xl font-semibold tabular-nums leading-none">{value}</div>
        <div className="mt-1.5 truncate text-xs text-muted-foreground">{label}</div>
      </div>
    </Card>
  );
}
