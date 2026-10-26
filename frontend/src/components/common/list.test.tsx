import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/render";
import { VirtualTable } from "./VirtualTable";
import { flatItems, useCursorList } from "./useCursorList";

interface Row {
  id: number;
}
const cols = [{ id: "id", header: "ID", cell: (r: Row) => String(r.id) }];
const mk = (from: number, n: number): Row[] => Array.from({ length: n }, (_, i) => ({ id: from + i }));

function Harness() {
  const q = useCursorList<Row>("targets", { q: "x" });
  const rows = flatItems(q);
  return (
    <VirtualTable
      rows={rows}
      columns={cols}
      getRowId={(r) => r.id}
      onEndReached={() => {
        if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
      }}
    />
  );
}

describe("cursor list", () => {
  it("fetches next page on end reached", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/targets", ({ request }) => {
        const u = new URL(request.url);
        seen.push(u.searchParams.get("cursor"));
        expect(u.searchParams.get("limit")).toBe("100");
        return u.searchParams.get("cursor")
          ? HttpResponse.json({ items: mk(25, 5), next_cursor: null })
          : HttpResponse.json({ items: mk(0, 25), next_cursor: "c2" });
      }),
    );
    renderWithProviders(<Harness />);
    await waitFor(() => expect(screen.getByRole("table")).toHaveAttribute("aria-rowcount", "31"));
    expect(seen).toEqual([null, "c2"]);
  });
});

describe("virtual table", () => {
  it("renders under 100 rows for 10000", async () => {
    renderWithProviders(<VirtualTable rows={mk(0, 10000)} columns={cols} getRowId={(r) => r.id} />);
    const n = (await screen.findAllByRole("row")).length;
    expect(n).toBeGreaterThan(0);
    expect(n).toBeLessThan(100);
  });

  it("calls onEndReached near the end", async () => {
    let called = 0;
    renderWithProviders(
      <VirtualTable rows={mk(0, 10)} columns={cols} getRowId={(r) => r.id} onEndReached={() => called++} />,
    );
    await waitFor(() => expect(called).toBeGreaterThan(0));
  });
});
