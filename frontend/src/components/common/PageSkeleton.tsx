export function PageSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="animate-pulse space-y-4 p-4">
      <div className="h-7 w-1/3 rounded bg-muted" />
      <div className="h-24 rounded bg-muted" />
      <div className="h-24 rounded bg-muted" />
    </div>
  );
}
