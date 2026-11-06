import { blockingProblems, controlsFor, runProblems, searchSummary, type PersonPreview } from "../claimSetup";

const p = (over: Partial<PersonPreview>): PersonPreview => ({
  status: "searchable", age: 62, entered_age: 67, receiving: false, pia: 2000,
  ages: [], exclusions: [], message: null, ...over,
});

// A salaried couple: self 65–70 (63–64 overlap salary), spouse 64–70 (62–63).
const samplePlan = {
  self: p({ entered_age: 68, ages: [65, 66, 67, 68, 69, 70],
            exclusions: [63, 64].map((age) => ({ age, reason: "salary paid 2026–2027, before full retirement age" })) }),
  spouse: p({ entered_age: 66, ages: [64, 65, 66, 67, 68, 69, 70],
              exclusions: [62, 63].map((age) => ({ age, reason: "salary paid 2028–2029, before full retirement age" })) }),
};

test("the review's preview for a salaried couple", () => {
  const s = searchSummary(samplePlan, { self: "search", spouse: "search" });
  expect(s.headline).toBe("Compare 42 claim-age combinations");
  expect(s.people).toEqual([
    "You: searching ages 65–70 (compared with 68)",
    "Spouse: searching ages 64–70 (compared with 66)",
  ]);
  expect(s.exclusionNote).toMatch(/salary is paid before full retirement age/);
  expect(s.exclusionNote).toMatch(/not prohibited/);
  expect(s.comparison).toBe("Compare against your entered ages: 68 and 66.");
  expect(s.actionLabel).toBe("Optimize conversions and claim ages");
  expect(s.estimate).toBe("About 3 minutes");
});

test("both fixed is a conversion optimization with the ages named", () => {
  const s = searchSummary(samplePlan, { self: "fixed", spouse: "fixed" });
  expect(s.searching).toBe(false);
  expect(s.headline).toBe("Social Security ages held fixed");
  expect(s.people).toEqual(["You: 68 (your chosen age)", "Spouse: 66 (your chosen age)"]);
  expect(s.actionLabel).toBe("Optimize conversions");
  expect(controlsFor(samplePlan, { self: "fixed", spouse: "fixed" })).toEqual({
    self: { mode: "fixed" }, spouse: { mode: "fixed" },
  });
});

test("one person searched; a receiving person is fixed whatever the mode says", () => {
  const preview = { self: samplePlan.self, spouse: p({ status: "receiving", entered_age: 64, ages: [64] }) };
  const s = searchSummary(preview, { self: "search", spouse: "search" });
  expect(s.headline).toBe("Compare 6 claim-age combinations");
  expect(s.people[1]).toBe("Spouse: 64 (already receiving — fixed)");
  expect(controlsFor(preview, { self: "search", spouse: "search" })).toEqual({
    self: { mode: "search" }, spouse: { mode: "fixed" },
  });
});

test("unanswered or contradictory inputs block the run, with the reason", () => {
  const preview = {
    self: p({ status: "needs_answer", message: "Say whether benefits have started" }),
    spouse: null,
  };
  expect(blockingProblems(preview)).toEqual(["You: Say whether benefits have started"]);
  expect(blockingProblems({ self: null, spouse: null, error: "stale plan" })).toEqual(["stale plan"]);
});

test("a fixed age skipped by the search blocks a mixed setup, not a fully fixed one", () => {
  const preview = {
    self: p({ entered_age: 64, ages: [65, 66, 67, 68, 69, 70],
              exclusions: [{ age: 64, reason: "salary paid 2028, before full retirement age" }] }),
    spouse: p({ entered_age: 67, ages: [62, 63, 64, 65, 66, 67, 68, 69, 70] }),
  };
  const mixed = runProblems(preview, { self: "fixed", spouse: "search" });
  expect(mixed).toHaveLength(1);
  expect(mixed[0]).toMatch(/^You: the chosen age 64 is skipped by the search \(salary paid 2028/);
  expect(runProblems(preview, { self: "fixed", spouse: "fixed" })).toEqual([]);
  expect(runProblems(preview, { self: "search", spouse: "fixed" })).toEqual([]);
});

test("a searched age with no comparison age says so, and invents none", () => {
  const plan = { ...samplePlan, spouse: { ...samplePlan.spouse!, entered_age: null } };
  const s = searchSummary(plan, { self: "search", spouse: "search" });
  expect(s.people[1]).toBe("Spouse: searching ages 64–70");
  expect(s.comparison).toMatch(/without a comparison with ages of your own/);
  expect(runProblems(plan, { self: "search", spouse: "search" })).toEqual([]);
});

test("an age to hold fixed must be chosen", () => {
  const plan = { ...samplePlan, self: { ...samplePlan.self!, entered_age: null } };
  expect(runProblems(plan, { self: "fixed", spouse: "search" })).toEqual([
    "You: choose a claim age, or let the optimizer find the best one.",
  ]);
});
