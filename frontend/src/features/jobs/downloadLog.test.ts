import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "../../test/server";
import { downloadLog } from "./downloadLog";

const ev = (id: number) => ({ id, ts: "2026-10-26T10:00:00Z", level: "info", type: "log", data: { msg: `m${id}` } });

describe("downloadLog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("download pages all events into ndjson in id order", async () => {
    const cursors: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/jobs/7/events", ({ request }) => {
        const u = new URL(request.url);
        cursors.push(u.searchParams.get("cursor"));
        expect(u.searchParams.get("min_level")).toBe("info");
        return u.searchParams.get("cursor")
          ? HttpResponse.json({ items: [ev(2), ev(1)], next_cursor: null })
          : HttpResponse.json({ items: [ev(4), ev(3)], next_cursor: "c2" });
      }),
    );
    let blob: Blob | undefined;
    URL.createObjectURL = vi.fn((b: Blob | MediaSource) => ((blob = b as Blob), "blob:x"));
    const revoke = vi.fn();
    URL.revokeObjectURL = revoke;
    let name = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      name = this.download;
    });
    await downloadLog(7, "info");
    expect(cursors).toEqual([null, "c2"]);
    expect(name).toBe("job-7.log.ndjson");
    const lines = (await blob!.text()).trim().split("\n").map((l) => JSON.parse(l) as { id: number });
    expect(lines.map((l) => l.id)).toEqual([1, 2, 3, 4]);
    expect(revoke).toHaveBeenCalledWith("blob:x");
  });
});
