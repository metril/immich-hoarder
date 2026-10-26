import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export const Route = createFileRoute("/_app/credentials")({
  component: lazyRouteComponent(() => import("../../features/credentials/CredentialsPage")),
  pendingComponent: PageSkeleton,
});
