export function PageSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="animate-pulse space-y-6">
      <div className="h-8 w-1/3 rounded-md bg-muted" />
      <div className="h-28 rounded-xl bg-muted" />
      <div className="h-28 rounded-xl bg-muted" />
    </div>
  );
}
