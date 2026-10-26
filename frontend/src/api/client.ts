import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

let onUnauthorized: () => void = () => {};

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function csrfToken(): string | null {
  for (const part of document.cookie.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === "ih_csrf") return decodeURIComponent(v.join("="));
  }
  return null;
}

const csrfAndAuth: Middleware = {
  onRequest({ request }) {
    if (MUTATING.has(request.method.toUpperCase())) {
      const t = csrfToken();
      if (t) request.headers.set("X-CSRF-Token", t);
    }
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401) onUnauthorized();
    return response;
  },
};

export const api = createClient<paths>({
  // Same-origin; the explicit origin lets Node/jsdom (tests) build absolute Request URLs.
  baseUrl: typeof location === "undefined" ? "" : location.origin,
  // Resolve fetch lazily so test-time interception (MSW) is honoured.
  fetch: (req) => globalThis.fetch(req),
});
api.use(csrfAndAuth);
