import type { ComponentProps } from "react";
import { cn } from "./cn";

/** Wrapper scrolls horizontally; header row sticks to the top of the wrapper. */
export function Table({ className, ...p }: ComponentProps<"table">) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full caption-bottom text-sm", className)} {...p} />
    </div>
  );
}
export function TableHeader({ className, ...p }: ComponentProps<"thead">) {
  return <thead className={cn("sticky top-0 z-10 bg-card [&_tr]:border-b", className)} {...p} />;
}
export function TableBody({ className, ...p }: ComponentProps<"tbody">) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...p} />;
}
export function TableRow({ className, ...p }: ComponentProps<"tr">) {
  return <tr className={cn("h-14 border-b transition-colors hover:bg-muted/50", className)} {...p} />;
}
export function TableHead({ className, ...p }: ComponentProps<"th">) {
  return (
    <th
      className={cn("h-11 px-4 text-left align-middle text-xs font-medium uppercase tracking-wide text-muted-foreground", className)}
      {...p}
    />
  );
}
export function TableCell({ className, ...p }: ComponentProps<"td">) {
  return <td className={cn("px-4 align-middle", className)} {...p} />;
}
