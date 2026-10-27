import { createFileRoute, redirect } from "@tanstack/react-router";
import { authStatusQuery } from "../api/authStatus";
import { meQuery } from "../api/me";
import LoginPage from "../features/auth/LoginPage";

export const Route = createFileRoute("/login")({
  beforeLoad: async ({ context }) => {
    if (await context.queryClient.ensureQueryData(meQuery)) throw redirect({ to: "/" });
    const status = await context.queryClient.fetchQuery({ ...authStatusQuery, staleTime: 0 });
    if (status.setup_required) throw redirect({ to: "/setup" });
  },
  component: LoginPage,
});
