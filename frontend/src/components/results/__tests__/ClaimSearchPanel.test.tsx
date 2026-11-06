/**
 * @jest-environment jsdom
 */
import "@testing-library/jest-dom";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ClaimSearchPanel, LongevityChecks, explorationSummary, longevitySummary } from "../ClaimSearchPanel";
import { ImprovementPanel } from "../ImprovementPanel";
import { SummaryCards } from "../SummaryCards";
import { AlternativesTable } from "../AlternativesTable";
import type { JointCandidate, JointSearch, OptimizationResult } from "@/lib/types";

const cand = (key: string, score: number, over: Partial<JointCandidate> = {}): JointCandidate => {
  const [policy_id, ages] = key.split("@");
  const [s, p] = ages.split("-").map(Number);
  return {
    key, policy_id, claim_age_self: s, claim_age_spouse: p, eligible: true,
    conversion_stop_year: null, total_conversions: 0, score,
    success_probability: 0.9, monte_carlo_paths: 300, fully_sampled: true, ...over,
  };
};

const row = (s: number, p: number, policy: string, stage1: number, over = {}) => ({
  key: `${s}-${p}`, claim_age_self: s, claim_age_spouse: p, eligible: true, entered: false,
  deterministic: { policy_id: policy, value: stage1, policies: 10 },
  stage1: { policy_id: policy, score: stage1, paths: 50 },
  final: null, ...over,
});

const winner = cand("level_5pct_thru_2029@70-70", 2_500_000, { conversion_stop_year: 2029 });
const search: JointSearch = {
  mode: "joint",
  controls: { self: { mode: "search", age: null }, spouse: { mode: "search", age: null } },
  exclusions: [{ person: "self", age: 68, reason: "salary through 2027" }],
  scenarios: [
    row(69, 69, "none", 2_480_000),
    row(69, 70, "fill_12_annual", 2_490_000, { entered: true }),
    row(70, 69, "none", 2_470_000),
    row(70, 70, "level_5pct_thru_2029", 2_505_000),
  ],
  stages: {
    stage1_runs: 50, winner_stage1_score: 2_505_000, final_runs: 300, candidates: 40,
    finalists: [winner, cand("none@70-70", 2_490_000)], per_scenario_breadth: 3,
  },
  baselines: {
    entered_no_conversion: cand("none@69-70", 2_400_000),
    entered_best_conversion: cand("fill_12_annual@69-70", 2_450_000),
    winner_ages_no_conversion: cand("none@70-70", 2_490_000),
  },
  comparisons: {
    "none@70-70": { key: "none@70-70", verdict: "unresolved" } as JointSearch["comparisons"][string],
  },
  materiality: 6250,
  sensitivity: [
    { variant: "horizon_minus_5", results: [
      { key: winner.key, score: 2_100_000, success_probability: 0.95, vs_winner: 0 },
      { key: "none@70-70", score: 2_110_000, success_probability: 0.95, vs_winner: 10_000 },
    ] },
  ],
  assumptions: { ss_cola: null, seed: 42, magi_proxy_note: "MAGI look-back note." },
  schedules: {},
  timings_seconds: {},
};

const result = {
  status: "success", computation_time_seconds: 1, paths_evaluated: 10, monte_carlo_runs: 300,
  winning_policy: {
    policy_id: winner.policy_id, key: winner.key, claim_age_self: 70, claim_age_spouse: 70,
    lifetime_taxes_nominal: 1, lifetime_taxes_pv: 1, terminal_estate: 1,
    success_probability: 0.9, monte_carlo_paths: 300, score: 2_500_000, total_conversions: 1,
    projected_future_marginal_rate: 0.22,
    score_components: {
      basis: "monte_carlo", monte_carlo_paths: 300, estate_pv: 2_510_000, shortfall_pv: 10_000,
      discretionary_shortfall_pv: 0, shortfall_weight: 1, discretionary_shortfall_weight: 0.5,
      score: 2_500_000, lifetime_taxes_pv: 400_000,
    },
  },
  yearly_plan: [], alternative_policies: [], warnings: [],
  search, joint_winner: winner,
} as unknown as OptimizationResult;

test("the matrix is keyed by claim pair and labels the screening stage", () => {
  render(<ClaimSearchPanel result={result} />);
  expect(screen.getByText(/This grid shows the initial comparison using 50 market scenarios/))
    .toHaveTextContent(
      "The initial 50 market scenarios are included in the final 300. This grid shows the initial " +
      "comparison using 50 market scenarios. A strategy that looks better here may rank lower when " +
      "tested using all 300. Select a cell to inspect its results; this does not start another " +
      "calculation.");
  // Δ vs the winner's own stage-1 score on the same 50 paths.
  expect(within(screen.getByTestId("cell-69-69")).getByText("−$25,000")).toBeInTheDocument();
  expect(within(screen.getByTestId("cell-70-70")).getByText("recommended ages")).toBeInTheDocument();
  expect(screen.getByTestId("cell-69-70").className).toMatch(/outline/);
  expect(screen.getByTestId("cell-68-69")).toHaveTextContent("excluded");
});

test("a cell click inspects stored results and starts nothing", () => {
  const fetchSpy = jest.fn();
  (global as unknown as { fetch: unknown }).fetch = fetchSpy;
  render(<ClaimSearchPanel result={result} />);
  // The recommendation's pair is shown first.
  expect(screen.getByTestId("cell-detail")).toHaveTextContent("You 70 · Spouse 70");
  expect(screen.getByTestId("cell-detail")).toHaveTextContent("Recommended ages");

  const btn = within(screen.getByTestId("cell-69-70")).getByRole("button");
  fireEvent.click(btn);
  expect(btn).toHaveAttribute("aria-pressed", "true");
  const detail = screen.getByTestId("cell-detail");
  expect(detail).toHaveTextContent("You 69 · Spouse 70");
  expect(detail).toHaveTextContent("Your entered ages");
  expect(detail).toHaveTextContent("StrategyFill the 12% bracket every year");
  expect(screen.getByTestId("cell-detail-comparison")).toHaveTextContent(
    "Screened during the search; not selected for detailed comparison.");
  // Sample counts and the separate figures sit under Technical details.
  const tech = screen.getByTestId("cell-detail-technical");
  expect(tech).toHaveTextContent("First 50 market scenarios");
  expect(tech).toHaveTextContent("−$15,000 vs the recommendation in the same scenarios");
  expect(detail.textContent!.indexOf("First 50 market scenarios")).toBeGreaterThan(
    detail.textContent!.indexOf("Compared with the recommendation"));
  expect(within(detail).queryByRole("button")).not.toBeInTheDocument();

  // An excluded age says why, in the detail rather than only on hover.
  fireEvent.click(within(screen.getByTestId("cell-68-69")).getByRole("button"));
  expect(screen.getByTestId("cell-detail-excluded")).toHaveTextContent("You at 68: salary through 2027");
  expect(fetchSpy).not.toHaveBeenCalled();
});

test("a pair carried to the full sample shows its comparison and paired verdict", () => {
  const r = {
    ...result,
    search: { ...search,
      scenarios: search.scenarios.map((s) => s.key === "69-69"
        ? { ...s, final: { policy_id: "none", score: 2_490_000, paths: 300 } } : s),
      comparisons: { ...search.comparisons,
        "none@69-69": { key: "none@69-69", verdict: "equivalent" } as JointSearch["comparisons"][string] },
    },
  } as unknown as OptimizationResult;
  render(<ClaimSearchPanel result={r} />);
  fireEvent.click(within(screen.getByTestId("cell-69-69")).getByRole("button"));
  expect(screen.getByTestId("cell-detail-comparison")).toHaveTextContent(
    "$10,000 lower modeled score than the recommendation · Practically equivalent");
});

test("the recommended pair: its own winner is the recommendation; a different screening pick is compared, not called the reference", () => {
  const r = {
    ...result,
    search: { ...search, scenarios: search.scenarios.map((s) => s.key === "70-70"
      ? { ...s, stage1: { policy_id: "none", score: 2_508_000, paths: 50 },
          final: { policy_id: winner.policy_id, score: winner.score, paths: 300 } } : s) },
  } as unknown as OptimizationResult;
  render(<ClaimSearchPanel result={r} />);
  expect(screen.getByTestId("cell-detail-comparison")).toHaveTextContent("This is the recommendation.");
  const tech = screen.getByTestId("cell-detail-technical");
  expect(tech).toHaveTextContent("No conversions: +$3,000 vs the recommendation in the same scenarios");
  expect(tech).not.toHaveTextContent("own screening result");
});

test("an older run without the screening reference never compares against the full-sample score", () => {
  const r = {
    ...result,
    search: { ...search, stages: { ...search.stages, winner_stage1_score: undefined } },
  } as unknown as OptimizationResult;
  render(<ClaimSearchPanel result={r} />);
  // 2,480,000 − winner.score (2,500,000) would read −$20,000: a mismatched comparison.
  expect(within(screen.getByTestId("cell-69-69")).queryByText("−$20,000")).not.toBeInTheDocument();
  expect(within(screen.getByTestId("cell-69-69")).getByText("—")).toBeInTheDocument();
  expect(screen.getByText(/Screening comparison unavailable for this saved run\. Select a cell/)).toBeInTheDocument();
  fireEvent.click(within(screen.getByTestId("cell-69-69")).getByRole("button"));
  expect(screen.getByTestId("cell-detail-technical")).toHaveTextContent(
    "Screening comparison unavailable for this saved run.");
});

test("finalists live in the alternatives list; only unlisted ones (older runs) stay here", () => {
  render(<ClaimSearchPanel result={result} />);
  const fin = screen.getByTestId("joint-finalists");
  expect(fin).toHaveTextContent("No conversions · You 70 · Spouse 70: $2,490,000 (−$10,000) · Too close to distinguish");
  expect(explorationSummary(result)).toBe(
    "We compared 4 combinations of your and your spouse's claim ages using 50 market scenarios. " +
    "We then tested the 2 leading strategies, along with your baseline options, using 300 market scenarios.");

  const listed = {
    ...result,
    alternative_policies: [{ policy_id: "none", key: "none@70-70" }],
  } as unknown as OptimizationResult;
  render(<ClaimSearchPanel result={listed} />);
  expect(screen.getAllByTestId("claim-search-panel")[1]).not.toHaveTextContent("Other finalists");
});

test("longevity checks: a row per strategy, a column per check, readable labels", () => {
  const r = {
    ...result,
    search: { ...search, sensitivity: [
      ...search.sensitivity,
      { variant: "spouse_dies_78", results: [
        { key: "none@70-70", score: 1_900_000, success_probability: 0.95, vs_winner: -5_000 },
        { key: winner.key, score: 1_905_000, success_probability: 0.95, vs_winner: 0 },
      ] },
    ] },
  } as unknown as OptimizationResult;
  render(<LongevityChecks result={r} />);
  const table = screen.getByTestId("joint-sensitivity");
  expect(table).not.toHaveTextContent("@");
  const rec = screen.getByTestId(`longevity-row-${winner.key}`);
  expect(rec).toHaveTextContent("Recommendation: Convert up to 5% of the starting IRA each year through 2029");
  expect(rec).toHaveTextContent("You 70 · Spouse 70");
  // Cells follow the column's check, whatever order a check lists its results in.
  expect(rec).toHaveTextContent("$2,100,000");
  expect(rec).toHaveTextContent("$1,905,000");
  const alt = screen.getByTestId("longevity-row-none@70-70");
  expect(alt).toHaveTextContent("+$10,000");
  expect(alt).toHaveTextContent("−$5,000");
  expect(screen.getByTestId("longevity-holds")).toHaveTextContent("Highest among the strategies checked?NoYes");
  expect(longevitySummary(result)).toBe(
    "The recommendation is highest among the strategies checked in 0 of 1 checks of other plan " +
    "lengths and lifespans; in the others another strategy scores higher. These checks do not change the ranking."
  );
});

test("how much it helps: each comparison shows both outcomes and the difference", () => {
  // The best strategy at the entered ages (69/70) is fill_12: three comparisons.
  render(<ImprovementPanel result={result} />);
  const panel = screen.getByTestId("improvement-panel");
  const ages = within(panel).getByTestId("improvement-ages");
  expect(ages).toHaveTextContent("Your ages 69 / 70 → Recommended ages 70 / 70");
  expect(within(ages).getByTestId("improvement-ages-sentence")).toHaveTextContent(
    "Changing your claim ages from 69 / 70 to 70 / 70 improves the modeled result by $50,000. " +
    "Spending is funded in 270 of 300 market scenarios, compared with 270 using your entered ages. " +
    "At your entered ages the best strategy is fill the 12% bracket every year; the recommendation " +
    "is convert up to 5% of the starting IRA each year through 2029."
  );
  const score = within(ages).getByTestId("row-score");
  expect(score).toHaveTextContent("$2,450,000");
  expect(score).toHaveTextContent("$2,500,000");
  expect(score).toHaveTextContent("+$50,000");
  expect(within(ages).getByTestId("row-funded")).toHaveTextContent("270 of 300270 of 300no change");
  // Older baselines carry no breakdown: no estate rows rather than guesses.
  expect(within(ages).queryByTestId("row-estate")).not.toBeInTheDocument();
  const conv = within(panel).getByTestId("improvement-conversions");
  expect(conv).toHaveTextContent("Adding Roth conversions at ages 70 / 70 improves the modeled result by $10,000.");
  expect(conv).toHaveTextContent("The simulation does not clearly separate the two.");
  expect(within(conv).getByTestId("row-verdict")).toHaveTextContent("Too close to distinguish");
  expect(within(panel).getByTestId("improvement-combined")).toHaveTextContent("+$100,000");
  expect(panel).toHaveTextContent("do not add the differences together");
  expect(panel).toHaveTextContent("neither tax saved nor a guaranteed increase in your estate");
});

test("how much it helps: with no comparison age, only the conversion comparison", () => {
  const { entered_no_conversion: _n, entered_best_conversion: _b, ...baselines } = search.baselines;
  const r = {
    ...result, starting_traditional_balance: 1_000_000,
    search: { ...search, baselines, scenarios: search.scenarios.map((x) => ({ ...x, entered: false })) },
  } as unknown as OptimizationResult;
  render(<ImprovementPanel result={r} />);
  const panel = screen.getByTestId("improvement-panel");
  expect(within(panel).queryByTestId("improvement-ages")).not.toBeInTheDocument();
  expect(within(panel).queryByTestId("improvement-combined")).not.toBeInTheDocument();
  expect(within(panel).getByTestId("improvement-conversions")).toHaveTextContent(
    "No conversions → Convert up to $50,000 annually through 2029, at ages 70 / 70",
  );
  expect(panel).toHaveTextContent("No comparison claim ages were provided.");
});

test("with no comparison ages and no conversions, a single quiet note replaces the panel", () => {
  const { entered_no_conversion: _n, entered_best_conversion: _b, ...rest } = search.baselines;
  const w = { ...result.joint_winner, policy_id: "none" };
  const r = {
    ...result, joint_winner: w,
    winning_policy: { ...result.winning_policy, policy_id: "none" },
    search: { ...search, baselines: { ...rest, winner_ages_no_conversion: w },
              scenarios: search.scenarios.map((x) => ({ ...x, entered: false })) },
  } as unknown as OptimizationResult;
  render(<ImprovementPanel result={r} />);
  expect(screen.queryByTestId("improvement-panel")).not.toBeInTheDocument();
  const notes = screen.getAllByTestId("improvement-note");
  expect(notes.map((n) => n.textContent)).toEqual(["No comparison claim ages were provided."]);
});

test("how much it helps: the score difference is broken into estate and unfunded spending", () => {
  const comps = (estate: number, score: number) =>
    ({ estate_pv: estate, shortfall_pv: estate - score, discretionary_shortfall_pv: 0 });
  const entered = cand("none@65-63", 2_847_044, { success_probability: 0.9467, score_components: comps(2_862_534, 2_847_044) });
  const w = cand("none@69-68", 3_000_820, { success_probability: 0.98, score_components: comps(3_004_868, 3_000_820) });
  const r = {
    ...result, joint_winner: w,
    winning_policy: { ...result.winning_policy, policy_id: "none", key: w.key, claim_age_self: 69, claim_age_spouse: 68 },
    search: { ...search, comparisons: { [entered.key]: { key: entered.key, verdict: "winner" } },
              baselines: { entered_no_conversion: entered, entered_best_conversion: entered,
                           winner_ages_no_conversion: w } },
  } as unknown as OptimizationResult;
  render(<ImprovementPanel result={r} />);
  const panel = screen.getByTestId("improvement-panel");
  expect(within(panel).getByTestId("improvement-ages-sentence")).toHaveTextContent(
    "Changing your claim ages from 65 / 63 to 69 / 68 improves the modeled result by $153,776. " +
    "Spending is funded in 294 of 300 market scenarios, compared with 284 using your entered ages. " +
    "Neither strategy makes Roth conversions."
  );
  expect(within(panel).getByTestId("row-estate")).toHaveTextContent("+$142,334");
  expect(within(panel).getByTestId("row-unfunded")).toHaveTextContent("$15,490$4,048−$11,442");
  expect(within(panel).getByTestId("row-verdict")).toHaveTextContent("Recommendation ahead");
  // One comparison: nothing to warn against adding up.
  expect(panel).not.toHaveTextContent("do not add");
  expect(within(panel).getByTestId("improvement-note")).toHaveTextContent(
    "The recommendation makes no Roth conversions, so there is no conversion benefit to measure."
  );
});

test("a fixed-age run compares against no conversions at the same ages", () => {
  const fixed = {
    ...result, search: undefined, joint_winner: undefined,
    claim_ages: { self: 69, spouse: 67 }, materiality: 6250,
    baseline_no_conversion: {
      policy_id: "none", score: 2_480_000, success_probability: 0.88, monte_carlo_paths: 300,
      score_difference: 20_000, is_recommendation: false,
      paired: { verdict: "winner" },
    },
  } as unknown as OptimizationResult;
  render(<ImprovementPanel result={fixed} />);
  const panel = screen.getByTestId("improvement-panel");
  expect(panel).toHaveTextContent(
    "No conversions → Convert up to 5% of the starting IRA each year through 2029, at ages 69 / 67"
  );
  expect(panel).toHaveTextContent("Adding Roth conversions at ages 69 / 67 improves the modeled result by $20,000.");
  expect(within(panel).getByTestId("row-score")).toHaveTextContent("$2,480,000$2,500,000+$20,000");
  expect(within(panel).getByTestId("row-funded")).toHaveTextContent("264 of 300270 of 300+6");
  expect(panel).toHaveTextContent("Recommendation ahead");
  // The label meanings live beside Close alternatives, where the labels are used.
  expect(within(panel).queryByTestId("verdict-details")).not.toBeInTheDocument();
});

test("a deterministic fixed-age run reports the score difference without path statistics", () => {
  const det = {
    ...result, search: undefined, joint_winner: undefined, monte_carlo_runs: 0,
    claim_ages: { self: 69, spouse: 67 }, materiality: 6250,
    winning_policy: { ...result.winning_policy, monte_carlo_paths: 1, success_probability: 1 },
    baseline_no_conversion: {
      policy_id: "none", score: 2_480_000, success_probability: 0, monte_carlo_paths: 1,
      score_difference: 20_000, is_recommendation: false, paired: { verdict: "winner" },
    },
  } as unknown as OptimizationResult;
  render(<ImprovementPanel result={det} />);
  const panel = screen.getByTestId("improvement-panel");
  expect(panel).toHaveTextContent("+$20,000");
  expect(panel).toHaveTextContent("Steady-return projection");
  expect(within(panel).getByTestId("row-score")).toHaveTextContent(/^Modeled score/);
  expect(within(panel).queryByTestId("row-funded")).not.toBeInTheDocument();
  expect(panel).not.toHaveTextContent("Recommendation ahead");
  expect(within(panel).queryByTestId("verdict-details")).not.toBeInTheDocument();
});

test("the summary states claim ages, the conversion and a Monte Carlo breakdown", () => {
  render(<SummaryCards result={result} planName="Sample plan" />);
  expect(screen.getByTestId("winning-policy-banner")).toHaveTextContent("Sample plan — Recommended strategy");
  expect(screen.getByTestId("recommendation-claim")).toHaveTextContent(
    "Claim Social Security at 70 for you and 70 for your spouse."
  );
  expect(screen.getByTestId("recommendation-conversion")).toHaveTextContent(", the last in 2029");
  const line = screen.getByTestId("score-components");
  expect(line).toHaveTextContent("averaged over 300 market scenarios");
  expect(line).toHaveTextContent("$2,510,000");
  expect(line).toHaveTextContent("= $2,500,000");
});

test("a joint alternative row shows its ages, read-only", () => {
  const alt = {
    policy_id: "none", key: "none@70-69", claim_age_self: 70, claim_age_spouse: 69,
    lifetime_taxes_delta: 0, terminal_estate_delta: 0, success_probability_delta: 0,
  };
  render(<AlternativesTable alternatives={[alt]} winningPolicyId="x" winnerSuccessProbability={0.9} />);
  expect(screen.getByTestId("alt-claim-ages")).toHaveTextContent("claim at You 70 · Spouse 69");
  expect(screen.getByTestId("alternatives-table")).not.toHaveTextContent("none@");
  expect(within(screen.getByTestId("alternatives-table")).queryByRole("button")).not.toBeInTheDocument();
});

test("a fixed-age result says its Social Security ages were held fixed", () => {
  const fixed = { ...result, search: undefined, joint_winner: undefined,
                  claim_ages: { self: 69, spouse: 67 } } as unknown as OptimizationResult;
  render(<SummaryCards result={fixed} />);
  expect(screen.getByTestId("winning-policy-banner")).toHaveTextContent(
    "Conversion optimization · recommended strategy"
  );
  expect(screen.getByTestId("recommendation-claim")).toHaveTextContent(
    "Social Security ages held fixed: You 69 · Spouse 67"
  );
});

test("when an alternative funds spending in more paths, the summary says why it still ranks lower", () => {
  const r = {
    ...result,
    alternative_policies: [{
      policy_id: "none", key: "none@70-69", lifetime_taxes_delta: 0, terminal_estate_delta: 0,
      success_probability_delta: 0.01, paired: { verdict: "unresolved" },
    }],
  } as unknown as OptimizationResult;
  render(<SummaryCards result={r} />);
  expect(screen.getByTestId("success-tradeoff")).toHaveTextContent("91% against 90%");
  expect(screen.getByTestId("success-tradeoff")).toHaveTextContent("not on that share alone");
});

test("exclusions are listed visibly, and a strategy most cells share is named once", () => {
  const r = {
    ...result,
    search: { ...search,
      exclusions: [
        { person: "self", age: 66, reason: "salary through 2027" },
        { person: "self", age: 67, reason: "salary through 2027" },
        { person: "self", age: 68, reason: "salary through 2027" },
      ],
      scenarios: search.scenarios.map((s) => ({ ...s, stage1: { ...s.stage1, policy_id: s.key === "70-70" ? s.stage1.policy_id : "none" } })),
    },
  } as unknown as OptimizationResult;
  render(<ClaimSearchPanel result={r} />);
  expect(screen.getByTestId("exclusion-list")).toHaveTextContent("You at 66–68: salary through 2027");
  expect(screen.getByTestId("matrix-legend")).toHaveTextContent("Cells without a strategy name: No conversions.");
  expect(screen.getByTestId("cell-69-69")).not.toHaveTextContent("No conversions");
  expect(screen.getByTestId("cell-70-70")).toHaveTextContent("Convert up to 5%");
});

test("a single filer's grid is a list of claim ages", () => {
  const r = {
    ...result,
    joint_winner: { ...winner, claim_age_spouse: null, key: "level_5pct_thru_2029@70--" },
    search: { ...search, exclusions: [],
      scenarios: [row(69, 0, "none", 2_480_000), row(70, 0, "none", 2_505_000)].map((x) => ({
        ...x, key: `${x.claim_age_self}--`, claim_age_spouse: null })) },
  } as unknown as OptimizationResult;
  render(<ClaimSearchPanel result={r} />);
  const m = screen.getByTestId("claim-age-matrix");
  expect(m).toHaveTextContent("Your claim age");
  expect(m).not.toHaveTextContent("Spouse");
});

test("the longevity tradeoff is stated beside the recommendation", () => {
  const r = {
    ...result,
    search: { ...search, sensitivity: [
      { variant: "spouse_dies_78", results: [
        { key: winner.key, score: 1, success_probability: 1, vs_winner: 0 },
        { key: "none@69-69", score: 1, success_probability: 1, vs_winner: 8_000 },
      ] },
      { variant: "horizon_plus_5", results: [
        { key: winner.key, score: 1, success_probability: 1, vs_winner: 0 },
        { key: "none@69-69", score: 1, success_probability: 1, vs_winner: -8_000 },
      ] },
    ] },
  } as unknown as OptimizationResult;
  render(<SummaryCards result={r} />);
  expect(screen.getByTestId("longevity-tradeoff")).toHaveTextContent(
    "In 1 of 2 lifespan checks (Spouse dies at 78) another strategy checked scores higher, " +
    "one that claims Social Security earlier. These checks do not change the ranking");
});
