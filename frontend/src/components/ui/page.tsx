import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";

export function PageContainer({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("mx-auto w-full max-w-7xl space-y-8 px-4 py-6 md:px-8 md:py-8", className)} {...p} />;
}

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-4", className)}>
      <div className="min-w-0">
        <h1 className="font-display text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
