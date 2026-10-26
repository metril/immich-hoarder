import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";
import { validateJobsSearch } from "../../features/jobs/search";

export const Route = createFileRoute("/_app/jobs/")({
  validateSearch: validateJobsSearch,
  component: lazyRouteComponent(() => import("../../features/jobs/JobsPage")),
  pendingComponent: PageSkeleton,
});
