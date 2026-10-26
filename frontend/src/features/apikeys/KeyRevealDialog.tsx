import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

/** Shows the plaintext once. The parent clears `secret` on close, so it is dropped from state. */
export function KeyRevealDialog({ secret, onClose }: { secret: string | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret ?? "");
      setCopied(true);
    } catch {
      toast.error("Could not copy; select the key and copy it manually");
    }
  };
  return (
    <Dialog
      open={secret !== null}
      onOpenChange={(o) => {
        if (!o) {
          setCopied(false);
          onClose();
        }
      }}
    >
      <DialogContent
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>API key created</DialogTitle>
          <DialogDescription className="font-medium text-destructive">This key will not be shown again</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <Input
            readOnly
            aria-label="API key"
            value={secret ?? ""}
            onFocus={(e) => e.currentTarget.select()}
            className="font-mono text-xs"
          />
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => void copy()}>
            {copied ? "Copied" : "Copy"}
          </Button>
          <DialogClose asChild>
            <Button>Done</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
