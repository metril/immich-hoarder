import { createFileRoute, redirect } from "@tanstack/react-router";
import { isAdmin, meQuery } from "../api/me";
import { AppLayout } from "../components/shell/AppLayout";
import { isAdminPath } from "../components/shell/nav";

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    const me = await context.queryClient.ensureQueryData(meQuery);
    if (!me) throw redirect({ to: "/login" });
    // Admin-only routes (NAV admin entries, == staticData.admin routes) bounce non-admins home.
    if (isAdminPath(location.pathname) && !isAdmin(me)) throw redirect({ to: "/" });
    return { me };
  },
  component: AppLayout,
});
