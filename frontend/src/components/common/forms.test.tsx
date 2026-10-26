import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { ApiError } from "../../api/errors";
import { FormField, inputClass } from "./FormField";
import { SecretInput } from "./SecretInput";
import { useApiForm } from "./useApiForm";

const schema = z.object({ name: z.string(), runtime: z.object({ retention_days: z.coerce.number() }) });

function F({ err }: { err: ApiError }) {
  const f = useApiForm(schema, {
    defaultValues: { name: "keep me", runtime: { retention_days: 5 } },
    onSubmit: () => {
      throw err;
    },
  });
  const e = f.formState.errors;
  return (
    <form onSubmit={f.submit}>
      <FormField label="Name" error={e.name?.message}>
        <input className={inputClass} {...f.register("name")} />
      </FormField>
      <FormField label="Retention" error={e.runtime?.retention_days?.message}>
        <input className={inputClass} {...f.register("runtime.retention_days")} />
      </FormField>
      {e.root?.message && <p>{e.root.message}</p>}
      <button>Save</button>
    </form>
  );
}

describe("useApiForm", () => {
  it("maps 422 detail to fields", async () => {
    const err = new ApiError(422, "bad", [], {
      "runtime.retention_days": "must be >= 1",
      name: "regex invalid",
    });
    render(<F err={err} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("must be >= 1")).toBeInTheDocument();
    expect(screen.getByText("regex invalid")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("keep me");
    expect(screen.getByLabelText("Name")).toBeInvalid();
    await waitFor(() => expect(screen.getByLabelText("Retention")).toHaveValue("5"));
  });
});

describe("SecretInput", () => {
  it("never prefilled and shows saved hint", async () => {
    render(<SecretInput saved aria-label="Secret" {...({ defaultValue: "leak", value: "leak2" } as object)} />);
    const i = screen.getByLabelText("Secret");
    expect(i).toHaveValue("");
    expect(i).toHaveAttribute("placeholder", "Saved — enter a new value to replace");
    expect(i).toHaveAttribute("autocomplete", "off");
    expect(i).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show value" }));
    expect(i).toHaveAttribute("type", "text");
  });
});
