import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FakeEventSource } from "./setup";
import { renderWithProviders } from "./render";

describe("test harness", () => {
  it("renders inside providers", async () => {
    renderWithProviders(<p>hello</p>);
    expect(await screen.findByText("hello")).toBeInTheDocument();
  });

  it("stubs EventSource and layout sizes", () => {
    const es = new EventSource("/x");
    expect(FakeEventSource.instances).toContain(es);
    expect(document.body.offsetHeight).toBe(800);
    expect(document.body.getBoundingClientRect().width).toBe(1024);
  });
});
