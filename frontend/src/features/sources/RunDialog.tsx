import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { Play } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../../components/ui/dialog";
import { Label } from "../../components/ui/label";
import { Select } from "../../components/ui/select";
import { RUN_LOG_LEVELS, activeJobId, jobNav, useRunSource } from "./hooks";

export function RunDialog({ sourceId, name }: { sourceId: number; name?: string }) {
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState("");
  const run = useRunSource();
  const navigate = useNavigate();
  const activeId = activeJobId(run.error);
  const reset = (o: boolean) => {
    setOpen(o);
    if (!o) run.reset();
  };
  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>
        <Button size="sm" aria-label={name ? `Run ${name}` : "Run"}>
          <Play aria-hidden /> Run
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Run now</DialogTitle>
          <DialogDescription className="min-w-0 break-words">{name ? `Start a job for ${name}.` : "Start a job for this source."}</DialogDescription>
        </DialogHeader>
        <DialogBody className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor={`run-level-${sourceId}`}>Log level</Label>
            <Select id={`run-level-${sourceId}`} value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">Source default</option>
              {RUN_LOG_LEVELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </Select>
          </div>
          {activeId !== null ? (
            <p role="alert" className="text-sm text-destructive">
              A job for this source is already queued or running.{" "}
              <Link to="/jobs/$jobId" params={{ jobId: String(activeId) }} className="underline">
                View job #{activeId}
              </Link>
            </p>
          ) : run.isError ? (
            <p role="alert" className="text-sm text-destructive">{run.error.message}</p>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            loading={run.isPending}
            onClick={() =>
              run.mutate(
                { id: sourceId, log_level: level || undefined },
                {
                  onSuccess: (job) => {
                    setOpen(false);
                    void navigate(jobNav(job.id));
                  },
                },
              )
            }
          >
            Start run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
