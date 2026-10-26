import { describe, expect, it } from "vitest";
import { validateSourcesSearch } from "../../routes/_app/sources";

describe("validateSourcesSearch", () => {
  it.each([
    [{ edit: 3 }, { edit: 3 }],
    [{ edit: "3" }, { edit: 3 }],
    [{ edit: 0 }, {}],
    [{ edit: -2 }, {}],
    [{ edit: "-2" }, {}],
    [{ edit: 1.5 }, {}],
    [{ edit: "abc" }, {}],
    [{ edit: null }, {}],
    [{ new: 1 }, { new: true }],
    [{ new: "1" }, { new: true }],
    [{ new: true }, { new: true }],
    [{ new: 0 }, {}],
    [{ new: "no" }, {}],
    [{ q: "cats" }, { q: "cats" }],
    [{ q: "" }, {}],
    [{ q: 5 }, {}],
  ])("%j -> %j", (input, out) => {
    expect(validateSourcesSearch(input)).toEqual(out);
  });
});
