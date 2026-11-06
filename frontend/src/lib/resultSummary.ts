/** The words a result page leads with: what is recommended, how much it helps,
 *  and how sure the simulation is. Pure functions of a stored result, so the
 *  wording is tested once and every screen says the same thing. */

import type {
  AlternativePolicy,
  JointCandidate,
  OptimizationResult,
  PairedComparison,
} from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { policyLabel } from "@/lib/policyLabels";

import { EQUIVALENT_MEANING, UNRESOLVED_MEANING, VERDICT_LABEL } from "@/lib/verdicts";

export { EQUIVALENT_MEANING, UNRESOLVED_MEANING, VERDICT_LABEL };
export { ALTERNATIVE_MEANING, WINNER_MEANING } from "@/lib/verdicts";

type Verdict = PairedComparison["verdict"];

export const isClose = (v: Verdict | undefined) => v === "unresolved" || v === "equivalent";

function ages(self?: number | null, spouse?: number | null): string {
  return [self, spouse].filter((a) => a != null).join(" / ");
}

/** "You 69 · Spouse 70" -- claim ages, named, wherever a candidate is listed. */
export function claimAgesLabel(self?: number | null, spouse?: number | null): string {
  return [
    self != null ? `You ${self}` : null,
    spouse != null ? `Spouse ${spouse}` : null,
  ].filter(Boolean).join(" · ");
}

/** A candidate key ("fill_12_annual@69-70") in words: strategy and ages. */
export function candidateKeyLabel(
  key: string,
  start?: number | null,
): { strategy: string; ages: string } {
  const [policyId, pair = ""] = key.split("@");
  // A person with no claim-age dimension is "-": "69--", "--70".
  const m = /^(\d+|-)-(\d+|-)$/.exec(pair);
  const age = (a: string | undefined) => (a == null || a === "-" ? null : Number(a));
  return { strategy: policyLabel(policyId, start), ages: m ? claimAgesLabel(age(m[1]), age(m[2])) : "" };
}

/** "Claim Social Security at 69 for you and 68 for your spouse." */
export function claimSentence(self?: number | null, spouse?: number | null): string | null {
  if (self == null && spouse == null) return null;
  if (spouse == null) return `Claim Social Security at ${self}.`;
  if (self == null) return `Your spouse claims Social Security at ${spouse}.`;
  return `Claim Social Security at ${self} for you and ${spouse} for your spouse.`;
}

/** "Social Security ages held fixed: You 69 · Spouse 67" */
export function fixedAgesSentence(self?: number | null, spouse?: number | null): string | null {
  const parts = [
    self != null ? `You ${self}` : null,
    spouse != null ? `Spouse ${spouse}` : null,
  ].filter(Boolean);
  return parts.length ? `Social Security ages held fixed: ${parts.join(" · ")}` : null;
}

/** The years a schedule actually converts in, as ranges: "2026–2027 and
 *  2029". A strategy's name says what it aims for ("annually through 2029");
 *  limits and spending can skip years, so the years are stated separately. */
export function conversionYears(plan: { year: number; conversion: number }[]): string | null {
  const years = plan.filter((y) => y.conversion > 0).map((y) => y.year);
  if (years.length === 0) return null;
  const runs: string[] = [];
  let lo = years[0];
  for (let i = 1; i <= years.length; i++) {
    if (i === years.length || years[i] !== years[i - 1] + 1) {
      const hi = years[i - 1];
      runs.push(lo === hi ? `${lo}` : `${lo}–${hi}`);
      if (i < years.length) lo = years[i];
    }
  }
  return listOf(runs, "and");
}

/** The conversion decision in one sentence. */
export function conversionSentence(r: OptimizationResult): string {
  const wp = r.winning_policy;
  if (wp.policy_id === "none" || !(wp.total_conversions > 0)) {
    return "No Roth conversions in this modeled plan.";
  }
  const years = conversionYears(r.yearly_plan);
  const stop = r.joint_winner?.conversion_stop_year ?? null;
  const year0 = wp.year0_conversion ?? r.yearly_plan[0]?.conversion ?? 0;
  return (
    `${policyLabel(wp.policy_id, r.starting_traditional_balance)}: ` +
    `${formatCurrency(wp.total_conversions)} converted in total` +
    (years ? `, in ${years}` : stop != null ? `, the last in ${stop}` : "") +
    `; ${year0 > 0 ? `${formatCurrency(year0)} this year` : "no Roth conversion this year"}.`
  );
}

/** Whether a market simulation ran. A deterministic run stores its single
 *  expected-return path as one "path", so the path count cannot tell. */
export const simulated = (r: OptimizationResult) => (r.monte_carlo_runs ?? 0) > 0;


const lower = (t: string) => t[0].toLowerCase() + t.slice(1);

/** "a, b or c" (or "and"). */
function listOf(items: string[], conj: "or" | "and"): string {
  return items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} ${conj} ${items[items.length - 1]}`;
}

/** Who the recommendation and its close alternatives are, named so a reader
 *  can find them in the table: by ages when only the ages differ. */
function closeNames(r: OptimizationResult, close: AlternativePolicy[]) {
  const wp = r.winning_policy;
  const joint = r.search?.mode === "joint";
  const wAges = ages(wp.claim_age_self, wp.claim_age_spouse);
  if (joint && close.every((a) => a.policy_id === wp.policy_id)) {
    return {
      subject: `Ages ${wAges}`, plural: true,
      names: (alts: AlternativePolicy[]) =>
        `ages ${listOf(alts.map((a) => ages(a.claim_age_self, a.claim_age_spouse)), "or")}`,
    };
  }
  const name = (a: AlternativePolicy) =>
    `“${policyLabel(a.policy_id, r.starting_traditional_balance)}”` +
    (joint ? ` at ages ${ages(a.claim_age_self, a.claim_age_spouse)}` : "");
  return {
    subject: "The recommendation", plural: false,
    names: (alts: AlternativePolicy[]) => listOf(alts.map(name), "or"),
  };
}

/** The close calls, named: "However, this simulation cannot clearly separate
 *  them from ages 68/67, 68/66 or 68/65." null when there are none. */
export function closeCallSentence(r: OptimizationResult): string | null {
  if (r.forced_policy || !simulated(r)) return null;
  const alts = r.alternative_policies.filter((a) => a.paired);
  const unresolved = alts.filter((a) => a.paired!.verdict === "unresolved");
  const equivalent = alts.filter((a) => a.paired!.verdict === "equivalent");
  if (unresolved.length + equivalent.length === 0) return null;
  const n = closeNames(r, [...unresolved, ...equivalent]);
  const them = n.plural ? "them" : "it";
  const parts: string[] = [];
  if (unresolved.length) {
    parts.push(`However, this simulation cannot clearly separate ${them} from ${n.names(unresolved)}.`);
  }
  if (equivalent.length) {
    parts.push(
      `${unresolved.length ? "It also treats" : "However, the simulation treats"} ${them} as ` +
      `practically equivalent to ${n.names(equivalent)}: ${lower(EQUIVALENT_MEANING)}`,
    );
  }
  return parts.join(" ");
}

/** How sure the simulation is that the recommendation is ahead. */
export function confidenceSentence(r: OptimizationResult): string | null {
  if (r.forced_policy) return null;
  if (!simulated(r)) {
    return "Chosen on the steady-return projection alone: no market simulation, so no measure of how close the alternatives are.";
  }
  const alts = r.alternative_policies.filter((a) => a.paired);
  if (alts.length === 0) return "Highest modeled score.";
  const ahead = alts.filter((a) => a.paired!.verdict === "alternative");
  if (ahead.length > 0) {
    // Can happen when the leader on the score's mean trails on its median.
    return `Highest modeled score, but ${ahead.length} alternative${ahead.length > 1 ? "s" : ""} come${
      ahead.length > 1 ? "" : "s"
    } out ahead in most market scenarios — compare them below.`;
  }
  const close = closeCallSentence(r);
  if (!close) {
    return "Highest modeled score, and ahead of each close alternative across the market scenarios.";
  }
  const closeAlts = alts.filter((a) => isClose(a.paired!.verdict));
  const n = closeNames(r, closeAlts);
  return `${n.subject} ${n.plural ? "have" : "has"} the highest average modeled score. ${close}`;
}

/** Some alternative funds spending in more paths than the recommendation. */
export function higherSuccessAlternative(r: OptimizationResult): AlternativePolicy | null {
  if (!simulated(r)) return null;
  return (
    r.alternative_policies
      .filter((a) => a.success_probability_delta > 0.004)
      .sort((a, b) => b.success_probability_delta - a.success_probability_delta)[0] ?? null
  );
}

// ---------------------------------------------------------------------------
// Improvement over the entered plan
// ---------------------------------------------------------------------------

/** One side of an improvement comparison, on the market scenarios (or the
 *  steady-return projection when none ran), in today's dollars. */
export interface Outcome {
  /** Column heading: "Your ages: 65 / 63". */
  label: string;
  score: number;
  /** After-tax estate, and the unfunded spending the score deducts; null on
   *  runs saved before the breakdown was recorded. */
  estate: number | null;
  unfunded: number | null;
  /** Scenarios with spending funded, of `scenarios`; null without a simulation. */
  funded: number | null;
  scenarios: number | null;
}

export interface Improvement {
  id: "ages" | "conversions" | "combined";
  /** "Your entered ages → Recommended ages". */
  title: string;
  /** The comparison in words, from the same figures as the table. */
  sentence: string;
  from: Outcome;
  to: Outcome;
  verdict: Verdict | null;
}

export interface ImprovementSummary {
  comparisons: Improvement[];
  /** Comparisons with nothing to measure, said in a line instead. */
  notes: string[];
}

type Scored = { score: number; success_probability: number; monte_carlo_paths?: number };
type Components = { estate_pv: number } | null | undefined;

function outcome(label: string, c: Scored, comps: Components, sim: boolean, paths: number): Outcome {
  const n = c.monte_carlo_paths ?? paths;
  return {
    label,
    score: c.score,
    estate: comps ? comps.estate_pv : null,
    // Whatever separates the estate from the score: the weighted shortfalls.
    unfunded: comps ? comps.estate_pv - c.score : null,
    funded: sim ? Math.round(c.success_probability * n) : null,
    scenarios: sim ? n : null,
  };
}

function changeClause(diff: number): string {
  if (Math.abs(diff) < 0.5) return "leaves the modeled result unchanged";
  return `${diff > 0 ? "improves" : "lowers"} the modeled result by ${formatCurrency(Math.abs(diff))}`;
}

function fundedClause(o: Improvement["to"], from: Improvement["from"], fromWords: string): string {
  if (o.funded == null || from.funded == null) return "";
  return ` Spending is funded in ${o.funded} of ${o.scenarios} market scenarios, compared with ` +
    `${from.funded} ${fromWords}.`;
}

function verdictClause(v: Verdict | null): string {
  if (v === "unresolved") return " The simulation does not clearly separate the two.";
  if (v === "equivalent") return " The difference is small enough to treat the two similarly.";
  return "";
}

/** "Neither strategy makes Roth conversions." -- what each side converts. */
function strategyClause(fromPolicy: string, toPolicy: string, fromWhere: string,
                        start?: number | null): string {
  const name = (id: string) => lower(policyLabel(id, start));
  if (fromPolicy === "none" && toPolicy === "none") return " Neither strategy makes Roth conversions.";
  if (fromPolicy === toPolicy) return ` Both use the same strategy: ${name(toPolicy)}.`;
  return ` ${fromWhere} the best strategy is ${name(fromPolicy)}; the recommendation is ` +
    `${name(toPolicy)}.`;
}

const NO_CONVERSION_NOTE =
  "The recommendation makes no Roth conversions, so there is no conversion benefit to measure.";

/** How much the recommendation helps, as explicit "from → to" comparisons
 *  with both outcomes shown. They overlap and must never be added together.
 *  Empty when the run predates them. */
export function improvementSummary(r: OptimizationResult): ImprovementSummary {
  const out: ImprovementSummary = { comparisons: [], notes: [] };
  if (r.forced_policy) return out;
  const sim = simulated(r);
  const wp = r.winning_policy;
  const paths = sim ? (wp.monte_carlo_paths ?? r.monte_carlo_runs) : 1;
  const verdictOf = (v: Verdict | undefined | null) => (sim && v ? v : null);
  const s = r.search;
  if (s?.mode === "joint" && r.joint_winner) {
    const w = r.joint_winner;
    const wComps = w.score_components ??
      (wp.score_components?.basis === "monte_carlo" ? wp.score_components : null);
    const { entered_best_conversion: best, entered_no_conversion: none, winner_ages_no_conversion: wn } =
      s.baselines;
    const wAges = ages(w.claim_age_self, w.claim_age_spouse);
    const start = r.starting_traditional_balance;
    const make = (id: Improvement["id"], title: string, base: JointCandidate, fromLabel: string,
                  toLabel: string, sentence: (from: Outcome, to: Outcome) => string): Improvement => {
      const from = outcome(fromLabel, base, base.score_components, sim, paths);
      const to = outcome(toLabel, w, wComps, sim, paths);
      const verdict = verdictOf(s.comparisons[base.key]?.verdict);
      return { id, title, from, to, verdict, sentence: sentence(from, to) + verdictClause(verdict) };
    };
    // No comparison age for someone: no "your ages" to compare with.
    const bestAges = best ? ages(best.claim_age_self, best.claim_age_spouse) : null;
    if (!best) {
      out.notes.push("No comparison claim ages were provided.");
    } else if (best.key === w.key) {
      out.notes.push("Your entered claim ages are the recommended ages.");
    } else if (bestAges !== wAges) {
      out.comparisons.push(make(
        "ages", `Your ages ${bestAges} → Recommended ages ${wAges}`, best,
        `Your ages: ${bestAges}`, `Recommended ages: ${wAges}`,
        (from, to) =>
          `Changing your claim ages from ${bestAges} to ${wAges} ${changeClause(to.score - from.score)}.` +
          fundedClause(to, from, "using your entered ages") +
          strategyClause(best.policy_id, w.policy_id, "At your entered ages", start),
      ));
    }
    if (wn.key === w.key) {
      out.notes.push(NO_CONVERSION_NOTE);
    } else {
      out.comparisons.push(make(
        "conversions", `No conversions → ${policyLabel(w.policy_id, start)}, at ages ${wAges}`, wn,
        "No conversions", "Recommendation",
        (from, to) =>
          `Adding Roth conversions at ages ${wAges} ${changeClause(to.score - from.score)}.` +
          fundedClause(to, from, "without conversions"),
      ));
    }
    if (best && none && best.key !== none.key && none.key !== w.key) {
      const noneAges = ages(none.claim_age_self, none.claim_age_spouse);
      out.comparisons.push(make(
        "combined", `Your ages ${noneAges} without conversions → Recommendation`, none,
        `Your ages: ${noneAges}, no conversions`, "Recommendation",
        (from, to) =>
          `Compared with claiming at ${noneAges} and converting nothing, the recommendation ` +
          `${changeClause(to.score - from.score)}.` +
          fundedClause(to, from, "that way"),
      ));
    }
    // Nothing compared: the banner already says no conversions are made.
    if (out.comparisons.length === 0) out.notes = out.notes.filter((n) => n !== NO_CONVERSION_NOTE);
    return out;
  }
  const b = r.baseline_no_conversion;
  if (!b) return out;
  if (b.is_recommendation) return out;
  const at = ages(r.claim_ages?.self, r.claim_ages?.spouse);
  const from = outcome("No conversions", b, b.score_components, sim, paths);
  const to = outcome("Recommendation", wp, b.recommendation_score_components, sim, paths);
  // The stored difference was taken on the same scenarios; prefer it.
  to.score = from.score + b.score_difference;
  const verdict = verdictOf(b.paired?.verdict);
  out.comparisons.push({
    id: "conversions",
    title: `No conversions → ${policyLabel(wp.policy_id, r.starting_traditional_balance)}${at ? `, at ages ${at}` : ""}`,
    from, to, verdict,
    sentence:
      `Adding Roth conversions${at ? ` at ages ${at}` : ""} ${changeClause(b.score_difference)}.` +
      fundedClause(to, from, "without conversions") + verdictClause(verdict),
  });
  return out;
}

// ---------------------------------------------------------------------------
// Ranking: the recommendation and its close alternatives on the simulation
// ---------------------------------------------------------------------------

export interface RankingRow {
  key: string;
  policyId: string;
  /** "You 68 · Spouse 67" on a claim-age search, else null. */
  ages: string | null;
  isRecommendation: boolean;
  /** Average modeled score; null when the alternative rests on fewer
   *  scenarios than the recommendation and stored no score of its own. */
  score: number | null;
  /** Alternative − recommendation on the same scenarios; 0 for the recommendation. */
  difference: number;
  funded: number;
  scenarios: number;
  verdict: Verdict | null;
  year0: number | null;
}

/** The recommendation and each alternative on the measurement that ranked
 *  them: the modeled score across the market scenarios. null when no
 *  simulation ran (the steady-return projection then did the ranking) or
 *  the run predates the paired comparison. */
export function rankingRows(r: OptimizationResult): RankingRow[] | null {
  if (!simulated(r) || r.alternative_policies.length === 0) return null;
  const wp = r.winning_policy;
  const joint = r.search?.mode === "joint";
  const wScore = r.joint_winner?.score ?? wp.score;
  const wPaths = wp.monte_carlo_paths ?? r.monte_carlo_runs;
  const agesOf = (c: { claim_age_self?: number | null; claim_age_spouse?: number | null }) =>
    joint ? claimAgesLabel(c.claim_age_self, c.claim_age_spouse) : null;
  const rows: RankingRow[] = [{
    key: wp.key ?? wp.policy_id, policyId: wp.policy_id, ages: agesOf(wp), isRecommendation: true,
    score: wScore, difference: 0, funded: Math.round(wp.success_probability * wPaths),
    scenarios: wPaths, verdict: null,
    year0: wp.year0_conversion ?? r.yearly_plan[0]?.conversion ?? null,
  }];
  for (const a of r.alternative_policies) {
    // The paired difference is taken on the scenarios both were scored on.
    const difference = a.paired ? -a.paired.mean_difference : a.score != null ? a.score - wScore : null;
    if (difference == null) return null;
    const n = a.monte_carlo_paths ?? wPaths;
    rows.push({
      key: a.key ?? a.policy_id, policyId: a.policy_id, ages: agesOf(a), isRecommendation: false,
      score: a.score ?? (n === wPaths ? wScore + difference : null),
      difference,
      funded: Math.round((wp.success_probability + a.success_probability_delta) * n),
      scenarios: n,
      verdict: a.paired?.verdict ?? null,
      year0: a.year0_conversion ?? null,
    });
  }
  // Highest score first; on a forced run the plan shown may not lead.
  return rows.sort((x, y) => y.difference - x.difference || Number(y.isRecommendation) - Number(x.isRecommendation));
}

// ---------------------------------------------------------------------------
// Longevity checks
// ---------------------------------------------------------------------------

export const VARIANT_LABELS: Record<string, string> = {
  horizon_minus_5: "Plan ends 5 years earlier",
  horizon_plus_5: "Plan ends 5 years later",
  spouse_dies_78: "Spouse dies at 78",
  self_dies_78: "You die at 78",
};

/** The longevity tradeoff, in one sentence for beside the recommendation:
 *  which checks another checked strategy wins, and whether those strategies
 *  claim earlier. null when the recommendation holds in every check. */
export function longevityTradeoff(r: OptimizationResult): string | null {
  const s = r.search;
  const w = r.joint_winner;
  if (s?.mode !== "joint" || !w || s.sensitivity.length === 0) return null;
  const lost = s.sensitivity
    .map((row) => ({ row, best: [...row.results].sort((a, b) => b.vs_winner - a.vs_winner)[0] }))
    .filter(({ best }) => best && best.vs_winner > 0);
  if (lost.length === 0) return null;
  // Earlier = no one later and someone earlier than the recommendation.
  const earlier = lost.every(({ best }) => {
    const m = /@(\d+|-)-(\d+|-)$/.exec(best.key);
    if (!m) return false;
    const pairs = [[m[1], w.claim_age_self], [m[2], w.claim_age_spouse]] as const;
    const diffs = pairs
      .filter(([a, wa]) => a !== "-" && wa != null)
      .map(([a, wa]) => Number(a) - (wa as number));
    return diffs.every((d) => d <= 0) && diffs.some((d) => d < 0);
  });
  const names = lost.map(({ row }) => VARIANT_LABELS[row.variant] ?? row.variant).join("; ");
  return (
    `In ${lost.length} of ${s.sensitivity.length} lifespan checks (${names}) another strategy ` +
    `checked scores higher${earlier ? ", one that claims Social Security earlier" : ""}. ` +
    "These checks do not change the ranking; see \u201cWhat if you live longer or shorter?\u201d below."
  );
}
