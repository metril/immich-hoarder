import { Outlet, createRootRouteWithContext } from "@tanstack/react-router";
import type { RouterContext } from "../router";

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  notFoundComponent: () => (
    <div className="p-6 text-center">
      <h1 className="text-lg font-semibold">Page not found</h1>
      <a href="/" className="text-sm underline">
        Go to dashboard
      </a>
    </div>
  ),
});
