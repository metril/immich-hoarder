import { TriangleAlert } from "lucide-react";
import { useAuthStatus } from "../../api/authStatus";

/** Global warning while the server runs with the break-glass override. */
export function BreakGlassBanner() {
  const { data } = useAuthStatus();
  if (!data?.break_glass) return null;
  return (
    <div role="alert" className="flex items-center gap-2 border-b border-destructive bg-destructive/10 px-4 py-2 text-sm text-destructive">
      <TriangleAlert className="size-4 shrink-0" aria-hidden />
      Break-glass mode is active: local login is forced on. Unset the override and restart once access is restored.
    </div>
  );
}
