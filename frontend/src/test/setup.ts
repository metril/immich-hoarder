import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";
import { server } from "./server";

configure({ asyncUtilTimeout: 3000 });

type Listener = (ev: MessageEvent | Event) => void;

export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  url: string;
  readyState = 0;
  onopen: Listener | null = null;
  onmessage: Listener | null = null;
  onerror: Listener | null = null;
  private listeners = new Map<string, Set<Listener>>();

  constructor(url: string | URL) {
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)?.add(fn);
  }
  removeEventListener(type: string, fn: Listener) {
    this.listeners.get(type)?.delete(fn);
  }
  /** Deliver a server event; `data` is JSON-encoded unless already a string. */
  emit(type: string, data: unknown, lastEventId = "") {
    this.readyState = 1;
    const ev = new MessageEvent(type, {
      data: typeof data === "string" ? data : JSON.stringify(data),
      lastEventId,
    });
    this.listeners.get(type)?.forEach((fn) => fn(ev));
    if (type === "message") this.onmessage?.(ev);
  }
  /** Simulate a connection error. */
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  /** Simulate a connection error; readyState 0 = reconnecting, 2 = closed for good. */
  fail(closed = false) {
    this.readyState = closed ? 2 : 0;
    const ev = new Event("error");
    this.onerror?.(ev);
    this.listeners.get("error")?.forEach((fn) => fn(ev));
  }
  close() {
    this.readyState = 2;
  }
  static reset() {
    FakeEventSource.instances = [];
  }
}

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  // jsdom has no layout; give virtualizers a viewport.
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 800 });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 1024 });
  HTMLElement.prototype.getBoundingClientRect = () =>
    ({ width: 1024, height: 800, top: 0, left: 0, right: 1024, bottom: 800, x: 0, y: 0, toJSON: () => ({}) });
  Element.prototype.scrollIntoView = () => {};
  window.scrollTo = () => {};
});

// "/" is the lazy dashboard; warm its chunk so cold imports do not eat findBy timeouts.
beforeAll(() => import("../features/dashboard/Dashboard"), 30_000);

beforeEach(() => FakeEventSource.reset());
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
