import { http, HttpResponse } from "msw";
import type { RequestHandler } from "msw";

const empty = () => HttpResponse.json({ items: [], next_cursor: null });

/** Per-test overrides use server.use(); nothing is mocked globally so unhandled requests error. */
export const handlers: RequestHandler[] = [];

/** Empty lists for the dashboard (landing route "/"); spread into server.use() in tests that render "/". */
export const dashboardDefaults: RequestHandler[] = [
  http.get("*/api/v1/jobs", empty),
  http.get("*/api/v1/sources", empty),
  http.get("*/api/v1/uploads", empty),
];
