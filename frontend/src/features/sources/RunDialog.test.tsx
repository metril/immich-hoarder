import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { RunDialog } from "./RunDialog";

const job = { id: 42 };

describe("RunDialog", () => {
  it("run navigates to job on 202", async () => {
    let body: unknown;
    server.use(
      http.post("*/api/v1/sources/3/run", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(job, { status: 202 });
      }),
    );
    const { router } = renderWithProviders(<RunDialog sourceId={3} name="Cats" />);
    await userEvent.click(await screen.findByRole("button", { name: "Run Cats" }));
    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs/42"));
    expect(body).toEqual({});
  });

  it("sends the chosen log level", async () => {
    let body: unknown;
    server.use(
      http.post("*/api/v1/sources/3/run", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(job, { status: 202 });
      }),
    );
    renderWithProviders(<RunDialog sourceId={3} name="Cats" />);
    await userEvent.click(await screen.findByRole("button", { name: "Run Cats" }));
    await userEvent.selectOptions(screen.getByLabelText("Log level"), "debug");
    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(body).toEqual({ log_level: "debug" }));
  });

  it("run 409 shows message with link to active job", async () => {
    server.use(
      http.post("*/api/v1/sources/3/run", () => HttpResponse.json({ detail: { msg: "active", job_id: 7 } }, { status: 409 })),
    );
    const { router } = renderWithProviders(<RunDialog sourceId={3} name="Cats" />);
    await userEvent.click(await screen.findByRole("button", { name: "Run Cats" }));
    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    expect(await screen.findByText(/already queued or running/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /job #7/ });
    expect(link).toHaveAttribute("href", "/jobs/7");
    expect(router.state.location.pathname).toBe("/");
  });
});
