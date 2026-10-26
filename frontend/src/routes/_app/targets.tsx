import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export interface TargetsSearch {
  new?: boolean;
}

// Hand-rolled validation: zod must stay out of the eager bundle (ruling R3).
export function validateTargetsSearch(s: Record<string, unknown>): TargetsSearch {
  return s.new === true || s.new === 1 || s.new === "1" || s.new === "true" ? { new: true } : {};
}

export const Route = createFileRoute("/_app/targets")({
  validateSearch: validateTargetsSearch,
  component: lazyRouteComponent(() => import("../../features/targets/TargetsPage")),
  pendingComponent: PageSkeleton,
});
