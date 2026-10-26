import { Link, useNavigate } from "@tanstack/react-router";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { activeJobId, useRunSource } from "../sources/hooks";
import { count, isTerminal, useCancelJob, useRetryJob, type JobOut } from "./hooks";

const btn = "rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50";

export function JobActions({ job }: { job: JobOut }) {
  const navigate = useNavigate();
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const rerun = useRunSource();
  const activeId = activeJobId(retry.error) ?? activeJobId(rerun.error);
  const terminal = isTerminal(job.status);
  const open = (id: number) => void navigate({ to: "/jobs/$jobId", params: { jobId: String(id) } });
  return (
    <div className="flex flex-wrap gap-2">
      {!terminal && (
        <ConfirmDialog
          title={`Cancel job #${job.id}?`}
          body="The job stops after the current item. Already uploaded items stay in Immich."
          confirmLabel="Cancel job"
          destructive
          onConfirm={async () => {
            await cancel.mutateAsync(job.id);
          }}
          trigger={<button type="button" className={btn}>Cancel</button>}
        />
      )}
      {terminal && count(job.counters, "failed") > 0 && (
        <button
          type="button"
          className={btn}
          disabled={retry.isPending}
          onClick={() => retry.mutate(job.id, { onSuccess: (j) => open(j.id) })}
        >
          Retry failed
        </button>
      )}
      {terminal && (
        <button
          type="button"
          className={btn}
          disabled={rerun.isPending}
          onClick={() => rerun.mutate({ id: job.source_id }, { onSuccess: (j) => open(j.id) })}
        >
          Re-run
        </button>
      )}
      {(retry.isError || rerun.isError) && (
        <p role="alert" className="w-full text-sm text-destructive">
          {(retry.error ?? rerun.error)?.message}
          {activeId !== null && (
            <>
              {" "}
              <Link to="/jobs/$jobId" params={{ jobId: String(activeId) }} className="underline">View job #{activeId}</Link>
            </>
          )}
        </p>
      )}
    </div>
  );
}
