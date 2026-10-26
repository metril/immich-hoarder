import { useState } from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { CronField } from "./CronField";

const user = userEvent.setup({ delay: null });

let last: string | null | undefined;
function Host({ initial = null }: { initial?: string | null }) {
  const [v, setV] = useState<string | null>(initial);
  return <CronField value={v} onChange={(x) => { last = x; setV(x); }} />;
}

beforeEach(() => {
  last = undefined;
  vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(0);
});
afterEach(() => vi.restoreAllMocks());

describe("CronField", () => {
  it("is manual by default", async () => {
    renderWithProviders(<Host />);
    await screen.findByLabelText("Frequency");
    expect(screen.getByRole("group", { name: "Schedule" })).toBeInTheDocument();
    expect(screen.getByLabelText("Frequency")).toHaveValue("manual");
    expect(screen.getByText(/only runs when started manually/i)).toBeInTheDocument();
  });

  it("daily builder emits cron, description and next runs", async () => {
    renderWithProviders(<Host />);
    await screen.findByLabelText("Frequency");
    await user.selectOptions(screen.getByLabelText("Frequency"), "daily");
    expect(last).toBe("0 3 * * *");
    expect(await screen.findByText("At 03:00")).toBeInTheDocument();
    expect(screen.getByText("Next runs:")).toBeInTheDocument();
    expect(screen.getByText(/Times in .*stored as UTC/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add time" }));
    expect(last).toBe("0 3,9 * * *");
  });

  it("weekly toggles keep at least one day", async () => {
    renderWithProviders(<Host initial="0 3 * * 0" />);
    await screen.findByLabelText("Frequency");
    const sun = screen.getByRole("button", { name: "Sunday" });
    expect(sun).toHaveAttribute("aria-pressed", "true");
    await user.click(sun);
    expect(sun).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Friday" }));
    expect(last).toBe("0 3 * * 0,5");
  });

  it("every N minutes", async () => {
    renderWithProviders(<Host />);
    await screen.findByLabelText("Frequency");
    await user.selectOptions(screen.getByLabelText("Frequency"), "minutes");
    expect(last).toBe("*/15 * * * *");
    await user.selectOptions(screen.getByLabelText("Every (minutes)"), "30");
    expect(last).toBe("*/30 * * * *");
  });

  it("opens unknown patterns in Custom and validates", async () => {
    renderWithProviders(<Host initial="*/7 * * * *" />);
    await screen.findByLabelText("Frequency");
    expect(screen.getByLabelText("Frequency")).toHaveValue("custom");
    const input = screen.getByLabelText("Schedule (cron)");
    expect(input).toHaveValue("*/7 * * * *");
    await user.clear(input);
    await user.type(input, "nope");
    expect(await screen.findByText("Invalid cron expression")).toBeInTheDocument();
  });

  it("accepts @aliases without error", async () => {
    renderWithProviders(<Host initial="@daily" />);
    await screen.findByLabelText("Frequency");
    expect(screen.getByLabelText("Schedule (cron)")).toHaveValue("@daily");
    expect(screen.queryByText("Invalid cron expression")).not.toBeInTheDocument();
    expect(screen.getByText("Next runs:")).toBeInTheDocument();
  });

  it("converts local time to UTC", async () => {
    vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(300); // UTC-5
    renderWithProviders(<Host initial="0 3 * * 2" />);
    await screen.findByLabelText("Frequency");
    // 03:00 Tue UTC = 22:00 Mon local
    expect(screen.getByRole("button", { name: "Monday" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("At")).toHaveValue("22:00");
  });
});
