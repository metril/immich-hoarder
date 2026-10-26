import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { keys } from "../api/keys";
import type { MeOut } from "../api/me";
import { RouterProvider, createMemoryHistory, createRootRoute, createRouter } from "@tanstack/react-router";
import { createAppRouter } from "../router";

interface Opts {
  me?: MeOut | null;
  /** Render the real route tree at this path (ignores `ui`). */
  route?: string;
}

/** Render `ui` inside a fresh QueryClient (retry off) and a memory-history router. */
export function renderWithProviders(ui: ReactElement | null, opts: Opts = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (opts.me !== undefined) queryClient.setQueryData(keys.me(), opts.me);
  const history = createMemoryHistory({ initialEntries: [opts.route ?? "/"] });
  const router =
    opts.route !== undefined
      ? createAppRouter(queryClient, history)
      : createRouter({ routeTree: createRootRoute({ component: () => ui }), history });
  return {
    queryClient,
    router,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router as ReturnType<typeof createAppRouter>} />
      </QueryClientProvider>,
    ),
  };
}
