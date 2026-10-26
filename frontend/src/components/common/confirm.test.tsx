import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { ConfirmDialog } from "./ConfirmDialog";

const user = userEvent.setup({ delay: null });

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

describe("ConfirmDialog", () => {
  it("toasts and stays open when onConfirm rejects", async () => {
    renderWithProviders(
      <ConfirmDialog
        title="Delete?"
        body="sure"
        confirmLabel="Delete"
        destructive
        onConfirm={() => Promise.reject(new Error("nope"))}
        trigger={<button>Open</button>}
      />,
    );
    await user.click(await screen.findByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith("nope"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
