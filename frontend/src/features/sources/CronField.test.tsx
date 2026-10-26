import { useState } from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../test/render";
import { CronField } from "./CronField";

let last: string | null = null;
function Host() {
  const [v, setV] = useState<string | null>(null);
  return <CronField value={v} onChange={(x) => { last = x; setV(x); }} />;
}

describe("CronField", () => {
  it("cron preset sets value and describes it", async () => {
    renderWithProviders(<Host />);
    await userEvent.click(await screen.findByRole("button", { name: "Daily 03:00" }));
    expect(last).toBe("0 3 * * *");
    expect(screen.getByLabelText("Schedule (cron)")).toHaveValue("0 3 * * *");
    expect(screen.getByText("At 03:00")).toBeInTheDocument();
  });

  it("invalid cron shows message", async () => {
    renderWithProviders(<Host />);
    await userEvent.type(await screen.findByLabelText("Schedule (cron)"), "nope");
    expect(await screen.findByText("Invalid cron expression")).toBeInTheDocument();
  });

  it("@ forms defer to the server", async () => {
    renderWithProviders(<Host />);
    await userEvent.type(await screen.findByLabelText("Schedule (cron)"), "@daily");
    expect(screen.getByText(/server will validate/i)).toBeInTheDocument();
    expect(screen.queryByText("Invalid cron expression")).not.toBeInTheDocument();
  });
});
