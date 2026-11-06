import { BRACKET_CAP_OPTIONS, bracketCapSelectValue } from "@/lib/brackets";

describe("bracket-cap options", () => {
  // REGRESSION: the wizard and What-if dropdowns started at 12%, so a 10%
  // cap -- the ceiling that pairs with "Fill the 10% bracket" -- could not
  // be chosen or shown, and the two lists were separate copies.
  it("offers every statutory bracket with a top, starting at 10%", () => {
    expect(BRACKET_CAP_OPTIONS.map((o) => o.label)).toEqual([
      "10% bracket",
      "12% bracket",
      "22% bracket",
      "24% bracket",
      "32% bracket",
      "35% bracket",
    ]);
  });

  it("maps a stored cap to its option however the API formats it", () => {
    // Constraints come back from JSON as strings ("0.12"); a 10% cap can
    // arrive as "0.1" or "0.10" and must select the same option.
    expect(bracketCapSelectValue("0.1")).toBe("0.1");
    expect(bracketCapSelectValue("0.10")).toBe("0.1");
    expect(bracketCapSelectValue(0.1)).toBe("0.1");
    expect(bracketCapSelectValue("0.12")).toBe("0.12");
    expect(bracketCapSelectValue(undefined)).toBe("none");
    expect(bracketCapSelectValue(null)).toBe("none");
  });
});
