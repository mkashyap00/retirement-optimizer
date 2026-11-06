import {
  claimSentence,
  closeCallSentence,
  confidenceSentence,
  rankingRows,
  conversionSentence,
  conversionYears,
  fixedAgesSentence,
  higherSuccessAlternative,
} from "../resultSummary";
import type { AlternativePolicy, OptimizationResult } from "../types";

const alt = (verdict: string, over: Partial<AlternativePolicy> = {}): AlternativePolicy =>
  ({
    policy_id: "fill_12_annual", lifetime_taxes_delta: 0, terminal_estate_delta: 0,
    success_probability_delta: 0, paired: { verdict } as AlternativePolicy["paired"], ...over,
  }) as AlternativePolicy;

const result = (over: Partial<OptimizationResult> = {}): OptimizationResult =>
  ({
    status: "success", computation_time_seconds: 1, paths_evaluated: 1, monte_carlo_runs: 300,
    winning_policy: {
      policy_id: "none", lifetime_taxes_nominal: 0, lifetime_taxes_pv: 0, terminal_estate: 0,
      success_probability: 0.98, score: 1, total_conversions: 0, projected_future_marginal_rate: 0.22,
      claim_age_self: 69, claim_age_spouse: 68,
    },
    yearly_plan: [], alternative_policies: [], warnings: [], ...over,
  }) as OptimizationResult;

test("claim and fixed-age sentences", () => {
  expect(claimSentence(69, 68)).toBe("Claim Social Security at 69 for you and 68 for your spouse.");
  expect(claimSentence(70, null)).toBe("Claim Social Security at 70.");
  expect(fixedAgesSentence(69, 67)).toBe("Social Security ages held fixed: You 69 · Spouse 67");
});

test("no conversions reads as a decision, not an absence", () => {
  expect(conversionSentence(result())).toBe("No Roth conversions in this modeled plan.");
});

test("a converting plan states the total, the years it converts and this year", () => {
  const r = result({
    winning_policy: { ...result().winning_policy, policy_id: "fill_22_thru_2029",
                      total_conversions: 300000, year0_conversion: 0 },
    yearly_plan: [{ year: 2026, conversion: 0 }, { year: 2028, conversion: 150000 },
                  { year: 2029, conversion: 150000 }] as OptimizationResult["yearly_plan"],
  });
  expect(conversionSentence(r)).toMatch(/\$300,000 converted in total, in 2028–2029; no Roth conversion this year\.$/);
});

test("the years actually converted are stated apart from the strategy's name", () => {
  const plan = [2026, 2027, 2028, 2029, 2030].map((year) => ({ year, conversion: year === 2028 ? 0 : 50000 }));
  expect(conversionYears(plan)).toBe("2026–2027 and 2029–2030");
  expect(conversionYears([{ year: 2026, conversion: 1 }])).toBe("2026");
  expect(conversionYears([{ year: 2026, conversion: 0 }])).toBeNull();
  const r = result({
    starting_traditional_balance: 1_000_000,
    winning_policy: { ...result().winning_policy, policy_id: "level_5pct_thru_2030",
                      total_conversions: 200000, year0_conversion: 50000 },
    yearly_plan: plan as OptimizationResult["yearly_plan"],
  });
  expect(conversionSentence(r)).toBe(
    "Convert up to $50,000 annually through 2030: $200,000 converted in total, " +
      "in 2026–2027 and 2029–2030; $50,000 this year.",
  );
});

test("confidence follows the paired verdicts, never claiming a win it cannot show", () => {
  expect(confidenceSentence(result({ alternative_policies: [alt("winner"), alt("winner")] })))
    .toBe("Highest modeled score, and ahead of each close alternative across the market scenarios.");
  expect(confidenceSentence(result({
    alternative_policies: [alt("unresolved"), alt("equivalent", { policy_id: "fill_22_annual" }), alt("winner")],
  }))).toBe(
    "The recommendation has the highest average modeled score. However, this simulation cannot " +
    "clearly separate it from “Fill the 12% bracket every year”. It also treats it as " +
    "practically equivalent to “Fill the 22% bracket every year”: the results are similar " +
    "enough to treat these options alike under the model’s comparison threshold."
  );
  expect(confidenceSentence(result({ forced_policy: "none" }))).toBeNull();
  expect(confidenceSentence(result({ monte_carlo_runs: 0 }))).toMatch(/steady-return projection alone/);
});

test("a claim-age search names its close calls by ages", () => {
  const at = (s: number, p: number, verdict = "unresolved", policy = "none") =>
    alt(verdict, { policy_id: policy, key: `${policy}@${s}-${p}`, claim_age_self: s, claim_age_spouse: p });
  const joint = (alts: AlternativePolicy[]) =>
    result({ search: { mode: "joint" } as OptimizationResult["search"], alternative_policies: alts });
  const r = joint([at(68, 67), at(68, 66), at(68, 65), at(68, 66, "winner", "level_5pct_thru_2029")]);
  expect(confidenceSentence(r)).toBe(
    "Ages 69 / 68 have the highest average modeled score. However, this simulation cannot " +
    "clearly separate them from ages 68 / 67, 68 / 66 or 68 / 65."
  );
  expect(closeCallSentence(r)).toMatch(/^However/);
  // A close call with another strategy is named by strategy and ages.
  expect(confidenceSentence(joint([at(68, 67), at(68, 66, "unresolved", "fill_12_annual")]))).toBe(
    "The recommendation has the highest average modeled score. However, this simulation cannot " +
    "clearly separate it from “No conversions” at ages 68 / 67 or " +
    "“Fill the 12% bracket every year” at ages 68 / 66."
  );
  expect(closeCallSentence(joint([at(68, 66, "winner")]))).toBeNull();
});

test("the ranking shows every strategy on the score that ranked it", () => {
  const paired = (mean_difference: number, verdict = "unresolved") =>
    ({ verdict, mean_difference } as AlternativePolicy["paired"]);
  const r = result({
    winning_policy: { ...result().winning_policy, score: 3_000_820, monte_carlo_paths: 300, key: "none@69-68" },
    search: { mode: "joint" } as OptimizationResult["search"],
    alternative_policies: [
      alt("unresolved", { key: "none@68-67", claim_age_self: 68, claim_age_spouse: 67, policy_id: "none",
                          score: 2_998_615, success_probability_delta: -0.0033, paired: paired(2_205) }),
      // An older fixed-age row: no stored score, the paired difference gives it.
      alt("winner", { success_probability_delta: -0.01, paired: paired(13_660, "winner") }),
    ],
  });
  const rows = rankingRows(r)!;
  expect(rows.map((x) => x.isRecommendation)).toEqual([true, false, false]);
  expect(rows[0]).toMatchObject({ score: 3_000_820, difference: 0, funded: 294, scenarios: 300, ages: "You 69 · Spouse 68" });
  expect(rows[1]).toMatchObject({ score: 2_998_615, difference: -2_205, funded: 293, verdict: "unresolved" });
  expect(rows[2]).toMatchObject({ score: 3_000_820 - 13_660, difference: -13_660, funded: 291 });
  // No simulation, or a row with nothing to rank it by: the older table.
  expect(rankingRows({ ...r, monte_carlo_runs: 0 })).toBeNull();
  expect(rankingRows(result({ alternative_policies: [alt("winner", { paired: undefined })] }))).toBeNull();
});

test("an alternative that funds spending in more paths is surfaced", () => {
  const safer = alt("unresolved", { success_probability_delta: 0.01 });
  expect(higherSuccessAlternative(result({ alternative_policies: [alt("winner"), safer] }))).toBe(safer);
  expect(higherSuccessAlternative(result({ alternative_policies: [alt("winner")] }))).toBeNull();
});

test("a deterministic run (one stored path) claims no market statistics", () => {
  // The backend's shape: runs=0 with the expected-return path stored as one path.
  const det = result({
    monte_carlo_runs: 0,
    alternative_policies: [alt("winner", { success_probability_delta: 0.5 })],
  });
  det.winning_policy = { ...det.winning_policy, monte_carlo_paths: 1 };
  expect(higherSuccessAlternative(det)).toBeNull();
  expect(confidenceSentence(det)).toMatch(/no market simulation/);
});
