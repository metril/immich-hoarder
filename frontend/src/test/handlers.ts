import { http, HttpResponse } from "msw";
import type { RequestHandler } from "msw";

const empty = () => HttpResponse.json({ items: [], next_cursor: null });

/** Default handlers; tests add per-case overrides with server.use(). */
export const handlers: RequestHandler[] = [
  // The dashboard is the landing route, so tests rendering "/" hit these.
  http.get("*/api/v1/jobs", empty),
  http.get("*/api/v1/sources", empty),
  http.get("*/api/v1/uploads", empty),
];
