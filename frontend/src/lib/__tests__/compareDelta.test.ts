import { describeDelta } from "@/lib/compareDelta";

// The delta cards used to show a signed A−B number with a sign rule beneath
// it ("Negative = Scenario A pays less tax"). A +$125,643 in red was read as
// "A pays less" — the opposite. Each card now says which scenario comes out
// ahead, in words.
describe("describeDelta", () => {
  it("names the scenario that pays less tax", () => {
    expect(describeDelta(125_642.7, "taxes")).toBe("Scenario B: $125,643 less tax");
    expect(describeDelta(-70_000, "taxes")).toBe("Scenario A: $70,000 less tax");
  });

  it("names the scenario that leaves the larger estate", () => {
    expect(describeDelta(252_200.04, "estate")).toBe("Scenario A: $252,200 larger estate");
    expect(describeDelta(-1_000, "estate")).toBe("Scenario B: $1,000 larger estate");
  });

  it("names the scenario more likely to succeed, in points", () => {
    expect(describeDelta(0.0133, "success")).toBe(
      "Scenario A: 1.3 pts more likely to succeed"
    );
    expect(describeDelta(-0.08, "success")).toBe(
      "Scenario B: 8.0 pts more likely to succeed"
    );
  });

  it("uses the page's own side names", () => {
    expect(describeDelta(-70_000, "taxes", { a: "Baseline", b: "Your changes" })).toBe(
      "Baseline: $70,000 less tax");
  });

  it("says so when the scenarios match, including sub-display differences", () => {
    expect(describeDelta(0, "taxes")).toBe("Same in both");
    expect(describeDelta(0.3, "estate")).toBe("Same in both"); // rounds to $0
    expect(describeDelta(0.0004, "success")).toBe("Same in both"); // 0.0 pts
  });
});
