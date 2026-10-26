import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { components } from "../../api/schema";
import { useTestTarget } from "./hooks";

export function TestResult({ r }: { r: components["schemas"]["TargetTestOut"] }) {
  if (r.ok) {
    return (
      <p role="status" className="font-medium text-success">
        Connected · Immich v{r.version ?? "?"}
      </p>
    );
  }
  return (
    <div role="status" className="space-y-2 text-destructive">
      <p>{r.error ?? "Connection failed"}</p>
      {r.missing_permissions.length > 0 && (
        <>
          <p className="text-sm">Missing permissions:</p>
          <ul className="list-disc pl-5 font-mono text-sm">
            {r.missing_permissions.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function TargetTestButton({ id, name }: { id: number; name: string }) {
  const [open, setOpen] = useState(false);
  const test = useTestTarget();
  const btnRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        ref={btnRef}
        size="sm"
        variant="outline"
        aria-label={`Test ${name}`}
        loading={test.isPending}
        onClick={() => {
          test.mutate(id, {
            onSuccess: () => setOpen(true),
            onError: (e) => toast.error(e.message),
          });
        }}
      >
        {test.isPending ? "Testing…" : "Test"}
      </Button>
      <DialogContent
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          btnRef.current?.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>Test {name}</DialogTitle>
          <DialogDescription className="sr-only">Connection test result</DialogDescription>
        </DialogHeader>
        <DialogBody>{test.data && <TestResult r={test.data} />}</DialogBody>
      </DialogContent>
    </Dialog>
  );
}
