import { createFileRoute, redirect } from "@tanstack/react-router";
import { authStatusQuery } from "../api/authStatus";
import { isAdmin, meQuery } from "../api/me";
import { AppLayout } from "../components/shell/AppLayout";

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, matches }) => {
    const me = await context.queryClient.ensureQueryData(meQuery);
    if (!me) {
      const status = await context.queryClient.fetchQuery(authStatusQuery).catch(() => null);
      throw redirect({ to: status?.setup_required ? "/setup" : "/login" });
    }
    // Case/slash-insensitive: driven by the matched routes' staticData, not the raw path.
    if (matches.some((m) => m.staticData?.admin) && !isAdmin(me)) throw redirect({ to: "/" });
    return { me };
  },
  component: AppLayout,
});
