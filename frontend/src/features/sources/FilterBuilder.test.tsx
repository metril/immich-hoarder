import { useState } from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../test/render";
import { FilterBuilder } from "./FilterBuilder";
import type { FilterSpec } from "./hooks";
import { emptyFilters } from "./schema";

let last: FilterSpec = emptyFilters();
function Host({ start = emptyFilters() }: { start?: FilterSpec }) {
  const [v, setV] = useState(start);
  return <FilterBuilder value={v} onChange={(x) => { last = x; setV(x); }} />;
}

describe("FilterBuilder", () => {
  it("filter builder empty inputs become null", async () => {
    renderWithProviders(<Host start={{ ...emptyFilters(), min_width: 100 }} />);
    await userEvent.clear(await screen.findByLabelText("Min width (px)"));
    expect(last.min_width).toBeNull();
    expect(screen.getByTestId("filter-summary")).toHaveTextContent("No filters active");
  });

  it("size units store bytes", async () => {
    renderWithProviders(<Host />);
    await userEvent.type(await screen.findByLabelText("Min size"), "2");
    expect(last.min_bytes).toBe(2048);
    await userEvent.selectOptions(screen.getByLabelText("Min size unit"), "MB");
    expect(last.min_bytes).toBe(2 * 1024 * 1024);
  });

  it("invalid regex shows error", async () => {
    renderWithProviders(<Host />);
    await userEvent.type(await screen.findByLabelText("Title include"), "(");
    expect(await screen.findByText("Invalid regular expression")).toBeInTheDocument();
  });
});
