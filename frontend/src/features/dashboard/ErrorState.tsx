import { Button } from "../../components/ui/button";

export function ErrorState({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-4 rounded-xl border border-danger/40 bg-danger/10 p-5 text-sm">
      <span className="min-w-0">Could not load {what}.</span>
      <Button variant="outline" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
