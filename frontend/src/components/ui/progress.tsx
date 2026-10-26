import { cn } from "./cn";

/** value 0-100; omit for indeterminate. `active` adds animated stripes. */
export function Progress({
  value,
  active,
  label,
  className,
}: {
  value?: number;
  active?: boolean;
  label?: string;
  className?: string;
}) {
  const pct = value === undefined ? undefined : Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <div
        className={cn(
          "h-full rounded-full bg-primary transition-[width] duration-300",
          active && "progress-stripes",
          pct === undefined && "w-1/3 motion-safe:animate-[ih-slide_1.4s_ease-in-out_infinite]",
        )}
        style={pct === undefined ? undefined : { width: `${pct}%` }}
      />
    </div>
  );
}
