import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export const Route = createFileRoute("/_app/")({
  component: lazyRouteComponent(() => import("../../features/dashboard/Dashboard")),
  pendingComponent: PageSkeleton,
});
