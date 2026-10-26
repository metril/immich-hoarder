import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export const Route = createFileRoute("/_app/api-keys")({
  component: lazyRouteComponent(() => import("../../features/apikeys/ApiKeysPage")),
  pendingComponent: PageSkeleton,
});
