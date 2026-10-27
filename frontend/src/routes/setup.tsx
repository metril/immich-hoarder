import { createFileRoute, redirect } from "@tanstack/react-router";
import { authStatusQuery } from "../api/authStatus";
import { meQuery } from "../api/me";
import SetupPage from "../features/auth/SetupPage";

export const Route = createFileRoute("/setup")({
  beforeLoad: async ({ context }) => {
    const status = await context.queryClient.fetchQuery({ ...authStatusQuery, staleTime: 0 });
    if (!status.setup_required && !status.reset_token_required) throw redirect({ to: (await context.queryClient.ensureQueryData(meQuery)) ? "/" : "/login" });
  },
  component: SetupPage,
});
