import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export interface SourcesSearch {
  edit?: number;
  new?: boolean;
  q?: string;
}

// Hand-rolled validation: zod must stay out of the eager bundle (ruling R3).
const posInt = (v: unknown) => {
  const n = typeof v === "string" ? Number(v) : v;
  return typeof n === "number" && Number.isInteger(n) && n > 0 ? n : undefined;
};

export function validateSourcesSearch(s: Record<string, unknown>): SourcesSearch {
  const out: SourcesSearch = {};
  const edit = posInt(s.edit);
  if (edit !== undefined) out.edit = edit;
  if (s.new === true || s.new === 1 || s.new === "1" || s.new === "true") out.new = true;
  if (typeof s.q === "string" && s.q) out.q = s.q;
  return out;
}

export const Route = createFileRoute("/_app/sources")({
  validateSearch: validateSourcesSearch,
  component: lazyRouteComponent(() => import("../../features/sources/SourcesPage")),
  pendingComponent: PageSkeleton,
});
