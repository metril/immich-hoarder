import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export const Route = createFileRoute("/_app/users")({
  staticData: { admin: true },
  component: lazyRouteComponent(() => import("../../features/users/UsersPage")),
  pendingComponent: PageSkeleton,
});
