import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { ExtractorHint } from "./ExtractorHint";

const setup = (url: string) => {
  server.use(http.get("*/api/v1/extractors", () => HttpResponse.json({ items: [{ category: "reddit", subcategories: [] }] })));
  renderWithProviders(<ExtractorHint url={url} />);
};

describe("ExtractorHint", () => {
  it("matches whole host labels", async () => {
    setup("https://old.reddit.com/r/x");
    expect(await screen.findByText("Supported: reddit", {}, { timeout: 2000 })).toBeInTheDocument();
  });
  it("never matches a substring", async () => {
    setup("https://notreddit.com/x");
    expect(await screen.findByText(/Not obviously supported/, {}, { timeout: 2000 })).toBeInTheDocument();
  });
});
