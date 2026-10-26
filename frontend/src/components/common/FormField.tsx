import { useId, type ReactElement, type ReactNode } from "react";
import { cloneElement } from "react";

/** Label + control + error. Control gets id, aria-invalid, aria-describedby. */
export function FormField({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: ReactNode;
  children: ReactElement<Record<string, unknown>>;
}) {
  const id = useId();
  const descId = `${id}-d`;
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {cloneElement(children, {
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error || hint ? descId : undefined,
      })}
      {error ? (
        <p id={descId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={descId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export const inputClass =
  "h-9 w-full rounded-md border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring aria-[invalid=true]:border-destructive";
