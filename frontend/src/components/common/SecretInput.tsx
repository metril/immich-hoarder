import { forwardRef, useId, useState, type InputHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "defaultValue"> & { saved: boolean };

/** Write-only secret field: never prefilled; hints when a value is already saved. */
export const SecretInput = forwardRef<HTMLInputElement, Props>(function SecretInput({ saved, className, ...props }, ref) {
  // Write-only: any value/defaultValue is dropped so a secret can never be prefilled.
  const { value: _v, defaultValue: _d, ...rest } = props as typeof props & { value?: unknown; defaultValue?: unknown };
  void _v;
  void _d;
  const [show, setShow] = useState(false);
  const hintId = useId();
  return (
    <div className="relative">
      <Input
        {...rest}
        ref={ref}
        type={show ? "text" : "password"}
        autoComplete="off"
        aria-describedby={saved ? hintId : rest["aria-describedby"]}
        placeholder={saved ? "Saved — enter a new value to replace" : rest.placeholder}
        className={`pr-10 ${className ?? ""}`}
      />
      {saved && (
        <span id={hintId} className="sr-only">
          Saved — enter a new value to replace
        </span>
      )}
      <Button
        variant="ghost"
        size="icon"
        aria-label={show ? "Hide value" : "Show value"}
        aria-pressed={show}
        onClick={() => setShow((s) => !s)}
        className="absolute right-0.5 top-0.5 size-8"
      >
        {show ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
      </Button>
    </div>
  );
});
