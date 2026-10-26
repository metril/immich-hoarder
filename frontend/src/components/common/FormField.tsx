import { useId, type ReactElement, type ReactNode } from "react";
import { cloneElement } from "react";
import { Label } from "@/components/ui/label";
import { controlClass } from "@/components/ui/input";

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
      <Label htmlFor={id}>{label}</Label>
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

export function FormRootError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-destructive p-2 text-sm text-destructive">
      {message}
    </p>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const inputClass = controlClass;
