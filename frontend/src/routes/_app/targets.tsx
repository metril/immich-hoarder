import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export const Route = createFileRoute("/_app/targets")({
  component: lazyRouteComponent(() => import("../../features/targets/TargetsPage")),
  pendingComponent: PageSkeleton,
});
