import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { dashboardDefaults } from "../../test/handlers";
import { server } from "../../test/server";

const user = userEvent.setup({ delay: null });

const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user", must_change_password: false };
const target = { id: 1, name: "Home", url: "https://immich.example", has_api_key: true, owner_id: 1, visibility: "private", can_edit: true, can_use: true };

function setup() {
  server.use(
    ...dashboardDefaults,
    http.head("*/api/v1/auth/login", () => new HttpResponse(null, { status: 204 })),
    http.get("*/api/v1/targets", () => HttpResponse.json({ items: [target], next_cursor: null })),
    http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })),
  );
  return renderWithProviders(null, { me, route: "/" });
}

async function openRip() {
  await screen.findByRole("navigation", { name: "Main" });
  await user.keyboard("{Control>}k{/Control}");
  const dlg = await screen.findByRole("dialog");
  await user.click(await within(dlg).findByText("Ad-hoc rip"));
  const rip = await screen.findByRole("dialog", { name: "Ad-hoc rip" });
  await screen.findByRole("option", { name: "Home" });
  return rip;
}

describe("RipDialog", () => {
  it("palette Ad-hoc rip submits POST /rip and navigates to the job", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/rip", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 9 }, { status: 202 });
      }),
    );
    const { router } = setup();
    const rip = await openRip();
    await user.type(within(rip).getByLabelText("URL"), "https://e.com/x");
    await user.selectOptions(within(rip).getByLabelText("Target"), "1");
    await user.click(within(rip).getByRole("button", { name: "Start rip" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs/9"));
    expect(body).toMatchObject({ url: "https://e.com/x", target_id: 1, visibility: "private" });
  });

  it("shows a 422 field error linked to its input", async () => {
    server.use(
      http.post("*/api/v1/rip", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "url"], msg: "not a supported url", type: "value_error" }] }, { status: 422 }),
      ),
    );
    setup();
    const rip = await openRip();
    await user.type(within(rip).getByLabelText("URL"), "nope");
    await user.selectOptions(within(rip).getByLabelText("Target"), "1");
    await user.click(within(rip).getByRole("button", { name: "Start rip" }));
    const err = await within(rip).findByText("not a supported url");
    const input = within(rip).getByLabelText("URL");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toBe(err.id);
  });
});
