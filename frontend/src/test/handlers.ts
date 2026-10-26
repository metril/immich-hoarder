import type { RequestHandler } from "msw";

/** Default handlers; tests add per-case overrides with server.use(). */
export const handlers: RequestHandler[] = [];
