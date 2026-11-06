import { changes, changeSummary } from "@/lib/whatIfChanges";

const base = {
  constraints: { irmaa_policy: "soft" as const, conversion_window: "anytime" as const, marginal_rate_limit: 0.22 },
  overrides: { required_spending: 90000, ss_claim_age_self: 67 },
};

test("lists only what differs, in words", () => {
  const b = {
    constraints: { ...base.constraints, marginal_rate_limit: "0.22" as unknown as number },
    overrides: { ...base.overrides, required_spending: 80000, ss_claim_age_self: 70 },
  };
  expect(changeSummary(changes(base, b))).toBe(
    "Annual spending $90,000 → $80,000 · Your claim age 67 → 70");
  expect(changes(base, base)).toEqual([]);
});

test("unset and default values compare equal", () => {
  const b = { constraints: { conversion_window: "anytime" as const, marginal_rate_limit: 0.22 },
              overrides: { ...base.overrides, spending_rule: "fixed" as const } };
  expect(changes(base, b)).toEqual([]);
});

test("Medicare surcharge settings compare by behaviour; strategies are named by amount", () => {
  const ignore = { ...base, constraints: { ...base.constraints, irmaa_policy: "ignore" as const } };
  expect(changes(ignore, base)).toEqual([]);
  const strict = { ...base, constraints: { ...base.constraints, irmaa_policy: "strict" as const } };
  expect(changeSummary(changes(ignore, strict))).toBe(
    "Medicare surcharge May cross surcharge thresholds → Restricted at surcharge thresholds");
  const level = { ...base, overrides: { ...base.overrides, policy_id: "level_10pct_thru_2030" } };
  expect(changeSummary(changes(base, level, 800_000))).toBe(
    "Strategy optimizer chooses → Convert up to $80,000 annually through 2030");
});

test("a floor left from trying 'cut back, then recover' is not a change", () => {
  // Cut back with a $135,000 floor, then back to keep spending the same: the
  // page hides the floor but keeps the typed value.
  const tried = { ...base, overrides: { ...base.overrides, spending_rule: "fixed" as const, spending_floor: 135000 } };
  expect(changes(base, tried)).toEqual([]);
  const cut = { ...base, overrides: { ...tried.overrides, spending_rule: "guardrails" as const } };
  expect(changeSummary(changes(base, cut))).toBe(
    "If markets go badly keep spending the same → cut back, then recover · Essential floor none → $135,000");
});
