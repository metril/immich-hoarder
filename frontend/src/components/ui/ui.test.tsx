import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Button } from "./button";
import { Switch } from "./switch";
import { Truncate } from "./truncate";

describe("ui primitives", () => {
  it("renders every Button variant", () => {
    const variants = ["primary", "secondary", "outline", "ghost", "destructive", "link"] as const;
    render(
      <>
        {variants.map((v) => (
          <Button key={v} variant={v}>
            {v}
          </Button>
        ))}
      </>,
    );
    for (const v of variants) expect(screen.getByRole("button", { name: v })).toBeInTheDocument();
  });

  it("Button loading disables", () => {
    render(<Button loading>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toBeDisabled();
  });

  it("Switch has role switch and toggles", async () => {
    function T() {
      const [on, setOn] = useState(false);
      return <Switch aria-label="active" checked={on} onCheckedChange={setOn} />;
    }
    render(<T />);
    const sw = screen.getByRole("switch", { name: "active" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    await userEvent.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "true");
  });

  it("Truncate sets title", () => {
    render(<Truncate>long text here</Truncate>);
    expect(screen.getByTitle("long text here")).toHaveClass("truncate", "min-w-0");
  });
});
