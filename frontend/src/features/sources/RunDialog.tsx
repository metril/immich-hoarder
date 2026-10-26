import { useState } from "react";
import { Dialog } from "radix-ui";
import { Link, useNavigate } from "@tanstack/react-router";
import { ApiError } from "../../api/errors";
import { inputClass } from "../../components/common/FormField";
import { RUN_LOG_LEVELS, jobNav, useRunSource } from "./hooks";

const btn = "rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring";

function activeJobId(e: unknown): number | null {
  if (!(e instanceof ApiError) || e.status !== 409) return null;
  const d = e.detail as { job_id?: unknown } | null;
  return typeof d?.job_id === "number" ? d.job_id : null;
}

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
    <Dialog.Root open={open} onOpenChange={reset}>
      <Dialog.Trigger className={btn} aria-label={name ? `Run ${name}` : "Run"}>
        Run
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-popover p-4 text-popover-foreground shadow-xl">
          <Dialog.Title className="text-base font-semibold">Run now</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">{name ? `Start a job for ${name}.` : "Start a job for this source."}</Dialog.Description>
          <div className="mt-3 grid gap-1.5">
            <label htmlFor={`run-level-${sourceId}`} className="text-sm font-medium">Log level</label>
            <select id={`run-level-${sourceId}`} className={inputClass} value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">Source default</option>
              {RUN_LOG_LEVELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
          {activeId !== null ? (
            <p role="alert" className="mt-3 text-sm text-destructive">
              A job for this source is already queued or running.{" "}
              <Link to={"/jobs/$jobId" as never} params={{ jobId: String(activeId) } as never} className="underline">
                View job #{activeId}
              </Link>
            </p>
          ) : run.isError ? (
            <p role="alert" className="mt-3 text-sm text-destructive">{run.error.message}</p>
          ) : null}
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close className={btn}>Cancel</Dialog.Close>
            <button
              type="button"
              disabled={run.isPending}
              className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
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
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
