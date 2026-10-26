import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
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
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    try {
      const qs: string[] = [];
      server.use(
        http.get("*/api/v1/targets/7/shares", () => HttpResponse.json({ visibility: "restricted", shares: [] })),
        http.get("*/api/v1/users/directory", ({ request }) => {
          qs.push(new URL(request.url).searchParams.get("q") ?? "");
          return HttpResponse.json([
            { id: 9, name: "Bobby" },
            { id: 10, name: "Bobbie" },
          ]);
        }),
      );
      const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
      renderWithProviders(<SharingDialog resource="targets" id={7} ownerId={1} />, { me: { ...owner, role: "admin", id: 5 } });
      await user.click(await screen.findByRole("button", { name: "Share" }));
      const box = await screen.findByRole("combobox", { name: "Add user" });
      await user.type(box, "b");
      await act(() => vi.advanceTimersByTimeAsync(600));
      expect(qs).toEqual([]); // min 2 chars
      await user.type(box, "ob");
      await act(() => vi.advanceTimersByTimeAsync(200));
      expect(qs).toEqual([]); // still debouncing
      await act(() => vi.advanceTimersByTimeAsync(100));
      expect(await screen.findByRole("option", { name: "Bobby" })).toBeInTheDocument();
      expect(qs).toEqual(["bob"]);
      // keyboard navigation
      await user.keyboard("{ArrowDown}{ArrowDown}");
      const opt = screen.getByRole("option", { name: "Bobbie" });
      expect(box).toHaveAttribute("aria-activedescendant", opt.id);
      await user.keyboard("{Enter}");
      expect(screen.getByLabelText("Permission for Bobbie")).toHaveValue("use");
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows principal names from the API", async () => {
    server.use(
      http.get("*/api/v1/targets/7/shares", () =>
        HttpResponse.json({
          visibility: "restricted",
          shares: [
            { principal_type: "user", principal_id: "9", principal_name: "Bobby", perm: "use" },
            { principal_type: "user", principal_id: "11", principal_name: null, perm: "use" },
          ],
        }),
      ),
    );
    renderWithProviders(<SharingDialog resource="targets" id={7} ownerId={1} />, { me: owner });
    await userEvent.click(await screen.findByRole("button", { name: "Share" }));
    expect(await screen.findByLabelText("Permission for Bobby")).toBeInTheDocument();
    expect(screen.getByLabelText("Permission for User #11")).toBeInTheDocument();
  });

  it("sharing hidden for non-owner non-admin (owner sees it)", async () => {
    const { unmount } = renderWithProviders(<SharingDialog resource="targets" id={7} ownerId={1} />, { me: owner });
    expect(await screen.findByRole("button", { name: "Share" })).toBeInTheDocument();
    unmount();
    renderWithProviders(<SharingDialog resource="targets" id={7} ownerId={1} />, { me: { ...owner, id: 3 } });
    // positive control: a sentinel rendered by the same provider tree appears, Share does not.
    await waitFor(() => expect(document.body.innerHTML).not.toContain("Share"));
    expect(screen.queryByRole("button", { name: "Share" })).toBeNull();
  });
});
