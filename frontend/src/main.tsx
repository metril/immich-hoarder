import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { setUnauthorizedHandler } from "./api/client";
import { keys } from "./api/keys";
import { installPreloadErrorGuard } from "./components/shell/reload";
import { createAppRouter } from "./router";
import "./styles.css";

const queryClient = new QueryClient();
// A 401 anywhere drops the session; the authed layout then redirects to /login.
setUnauthorizedHandler(() => queryClient.setQueryData(keys.me(), null));
const router = createAppRouter(queryClient);
installPreloadErrorGuard();

// A reload that fixed a stale-chunk error should not block a future one.
setTimeout(() => {
  try {
    sessionStorage.removeItem("ih-reloaded");
  } catch {
    /* storage unavailable */
  }
}, 10_000);

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
