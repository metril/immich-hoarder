import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export const Route = createFileRoute("/_app/jobs/$jobId")({
  component: lazyRouteComponent(() => import("../../features/jobs/JobDetail")),
  pendingComponent: PageSkeleton,
});
