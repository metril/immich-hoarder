import { http, HttpResponse } from "msw";
import type { RequestHandler } from "msw";

const empty = () => HttpResponse.json({ items: [], next_cursor: null });

/** Per-test overrides use server.use(); nothing is mocked globally so unhandled requests error. */
export const authStatus = (o: object = {}) =>
  http.get("*/api/v1/auth/status", () =>
    HttpResponse.json({ setup_required: false, oidc_enabled: true, local_login_enabled: false, break_glass: false, reset_token_required: false, ...o }),
  );

/** Default: set up, OIDC only. Tests override with server.use(authStatus({...})). */
export const handlers: RequestHandler[] = [authStatus()];

/** Empty lists for the dashboard (landing route "/"); spread into server.use() in tests that render "/". */
export const dashboardDefaults: RequestHandler[] = [
  http.get("*/api/v1/jobs", empty),
  http.get("*/api/v1/sources", empty),
  http.get("*/api/v1/uploads", empty),
];
