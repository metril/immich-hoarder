import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { MeOut } from "../../api/me";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/render";
import { SharingDialog } from "./SharingDialog";

const owner: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: ["ops"], role: "user" };

describe("SharingDialog", () => {
  it("sharing: restricted enables list, put sends entries", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.get("*/api/v1/targets/7/shares", () => HttpResponse.json({ visibility: "private", shares: [] })),
      http.put("*/api/v1/targets/7/shares", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(body);
      }),
    );
    renderWithProviders(<SharingDialog resource="targets" id={7} ownerId={1} />, { me: owner });
    await userEvent.click(await screen.findByRole("button", { name: "Share" }));
    const group = await screen.findByLabelText("Add group");
    expect(group.closest("fieldset")).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: "Restricted" }));
    expect(group.closest("fieldset")).toBeEnabled();
    await userEvent.type(group, "ops{Enter}");
    await userEvent.selectOptions(screen.getByLabelText("Permission for Group: ops"), "edit");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(body).toEqual({
        visibility: "restricted",
        shares: [{ principal_type: "group", principal_id: "ops", perm: "edit" }],
      }),
    );
  });

  it("sharing: directory search debounced and min 2 chars", async () => {
    const qs: string[] = [];
    server.use(
      http.get("*/api/v1/targets/7/shares", () => HttpResponse.json({ visibility: "restricted", shares: [] })),
      http.get("*/api/v1/users/directory", ({ request }) => {
        qs.push(new URL(request.url).searchParams.get("q") ?? "");
        return HttpResponse.json([{ id: 9, name: "Bobby" }]);
      }),
    );
    renderWithProviders(<SharingDialog resource="targets" id={7} ownerId={1} />, { me: { ...owner, role: "admin", id: 5 } });
    await userEvent.click(await screen.findByRole("button", { name: "Share" }));
    const box = await screen.findByRole("combobox", { name: "Add user" });
    await userEvent.type(box, "b");
    await new Promise((r) => setTimeout(r, 400));
    expect(qs).toEqual([]);
    await userEvent.type(box, "ob");
    expect(qs).toEqual([]); // debounced
    expect(await screen.findByRole("option", { name: "Bobby" })).toBeInTheDocument();
    expect(qs).toEqual(["bob"]);
    await userEvent.click(screen.getByRole("option", { name: "Bobby" }));
    expect(screen.getByLabelText("Permission for Bobby")).toHaveValue("use");
  });

  it("sharing hidden for non-owner non-admin", async () => {
    renderWithProviders(<SharingDialog resource="targets" id={7} ownerId={1} />, { me: { ...owner, id: 3 } });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("button", { name: "Share" })).toBeNull();
  });
});
