export function ErrorState({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-md border border-destructive/50 p-4 text-sm">
      <span>Could not load {what}.</span>
      <button type="button" onClick={onRetry} className="rounded-md border px-3 py-1.5 hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
        Retry
      </button>
    </div>
  );
}
