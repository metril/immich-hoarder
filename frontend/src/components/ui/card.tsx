import type { ComponentProps } from "react";
import { cn } from "./cn";

export function Card({ className, ...p }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card text-card-foreground shadow-card motion-safe:transition-shadow motion-safe:duration-150",
        className,
      )}
      {...p}
    />
  );
}
export function CardHeader({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-1 p-5 pb-0 md:p-6 md:pb-0", className)} {...p} />;
}
export function CardTitle({ className, ...p }: ComponentProps<"h2">) {
  return <h2 className={cn("font-display text-base font-semibold leading-tight", className)} {...p} />;
}
export function CardDescription({ className, ...p }: ComponentProps<"p">) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...p} />;
}
export function CardContent({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("min-w-0 p-5 md:p-6", className)} {...p} />;
}
export function CardFooter({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("flex items-center gap-2 p-5 pt-0 md:p-6 md:pt-0", className)} {...p} />;
}
