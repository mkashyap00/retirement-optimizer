"use client";

import type { AlternativePolicy } from "@/lib/types";
import type { RankingRow } from "@/lib/resultSummary";
import { formatCurrency } from "@/lib/utils";
import { pct } from "@/lib/marketModel";
import { policyLabel } from "@/lib/policyLabels";
import {
  ALTERNATIVE_MEANING,
  EQUIVALENT_MEANING,
  UNRESOLVED_MEANING,
  VERDICT_LABEL,
  WINNER_MEANING,
} from "@/lib/verdicts";

interface AlternativesTableProps {
  alternatives: AlternativePolicy[];
  winningPolicyId: string;
  /** The winner's absolute success probability (0–1). Alternatives store only
   *  a delta vs the winner, so we add it back to show each row's own value. */
  winnerSuccessProbability: number;
  /** The run's Monte Carlo scenario count; 0 means the simulation was
   *  skipped. Omitted by callers that predate it, which get the generic
   *  wording rather than a number that may be wrong. */
  monteCarloRuns?: number;
  /** The winner's own first-year conversion, the anchor for the spread note. */
  winnerYear0Conversion?: number;
  /** On a forced run, the policy the optimizer itself chose, tagged in its row
   *  so the recommendation is still visible from the pinned plan. */
  optimizerPickId?: string;
  /** The winner's first conversion year (null = never), for the note shown
   *  when every close strategy converts nothing this year. */
  winnerFirstConversionYear?: number | null;
  /** The projection's first year: the conversion column's year. */
  firstYear?: number;
  /** Every strategy on the modeled score across the market scenarios, the
   *  measurement that ranked them (lib/resultSummary rankingRows). When
   *  given it is the main table and the steady-return tax and estate
   *  figures move into a disclosure; null or omitted keeps the older
   *  single table (no simulation, or a run saved before paired comparison). */
  ranking?: RankingRow[] | null;
  /** The recommendation's lead and its close calls, in one sentence. */
  closeCall?: string | null;
  /** The steady-return projection's assumed annual return. */
  steadyReturn?: number | null;
  /** The run's starting traditional balance: names level-dollar rules by
   *  their amount. Absent on older runs. */
  startTraditional?: number | null;
  /** The dollar gap treated as immaterial ("Practically equivalent"). */
  materiality?: number | null;
}

/** "Roth conversion in 2026": the saved projection's own first year, so an
 *  older result still reads correctly. */
export function conversionHeading(year?: number): string {
  return year != null ? `Roth conversion in ${year}` : "Roth conversion, first year";
}

export function conversionTitle(year?: number): string {
  return `Amount transferred from traditional retirement accounts to Roth accounts in ${
    year != null ? year : "the first year of the plan"
  }.`;
}

/** Whether any strategy shown is a rule whose name needs explaining. */
function usesRuleNames(winner: string, alternatives: AlternativePolicy[]): boolean {
  return [winner, ...alternatives.map((a) => a.policy_id)].some((id) => id !== "none");
}

/** The range of this year's conversion across the winner and every
 *  alternative the paired test could not separate from it, or null when there
 *  is no such alternative (or no spread to report).
 *
 *  Close strategies agree on roughly how much to convert overall and can
 *  disagree by hundreds of thousands on how much to convert NOW. Year 0 is the
 *  only year a user acts on before re-running, so a single winner's amount
 *  overstates how settled that number is. */
export function year0Spread(
  alternatives: AlternativePolicy[],
  winnerYear0: number | undefined,
): { low: number; high: number } | null {
  if (winnerYear0 == null) return null;
  const close = alternatives
    .filter((a) => isCloseCall(a.paired?.verdict) && a.year0_conversion != null)
    .map((a) => a.year0_conversion as number);
  if (close.length === 0) return null;
  const all = [winnerYear0, ...close];
  const low = Math.min(...all);
  const high = Math.max(...all);
  return low === high ? null : { low, high };
}

/** What each comparison label concludes, in plain words; the statistics
 *  behind them sit under Technical details. Equivalent and too close are
 *  different conclusions and stay separate. */
function VerdictLegend({ materiality }: { materiality?: number | null }) {
  const rows: [string, string][] = [
    [VERDICT_LABEL.equivalent, EQUIVALENT_MEANING],
    [VERDICT_LABEL.unresolved, UNRESOLVED_MEANING],
    [VERDICT_LABEL.winner, WINNER_MEANING],
    [VERDICT_LABEL.alternative, ALTERNATIVE_MEANING],
  ];
  return (
    <details className="mt-2 text-sm text-muted-foreground" data-testid="verdict-details">
      <summary className="cursor-pointer font-medium text-primary">What the comparison labels mean</summary>
      <dl className="mt-2 space-y-1.5">
        {rows.map(([label, meaning]) => (
          <div key={label}>
            <dt className="inline font-medium text-foreground">{label}: </dt>
            <dd className="inline">{meaning}</dd>
          </div>
        ))}
      </dl>
      <details className="mt-2" data-testid="verdict-technical">
        <summary className="cursor-pointer font-medium text-primary">Technical details</summary>
        <div className="mt-2 space-y-1.5">
          <p>
            Each label compares a strategy with the recommendation scenario by scenario, on the
            same market scenarios, and takes a 95% confidence interval of the average difference.
          </p>
          <p>
            Practically equivalent: the whole interval lies within{" "}
            {materiality
              ? `±${formatCurrency(materiality)} (the larger of $5,000 and 0.25% of your assets)`
              : "the materiality threshold"}
            .
          </p>
          <p>
            Too close to distinguish: the interval includes zero, or the typical (median) scenario
            points the other way from the average.
          </p>
          <p>
            Recommendation ahead / Alternative ahead: the interval excludes zero and the median
            agrees with the average.
          </p>
        </div>
      </details>
    </details>
  );
}

/** "Too close to distinguish" or "practically equivalent": the simulation
 *  cannot rank the two, so the recommendation is not clearly ahead. */
export function isCloseCall(v: string | undefined): boolean {
  return v === "unresolved" || v === "equivalent";
}

/** The hover text behind a verdict badge, from the paired comparison. */
function verdictExplanation(p: NonNullable<AlternativePolicy["paired"]>): string {
  const range =
    `Across the market scenarios the recommendation's average lead is ` +
    `${formatCurrency(p.mean_difference)}, with a 95% range of ${formatCurrency(p.ci_low)} ` +
    `to ${formatCurrency(p.ci_high)}.`;
  switch (p.verdict) {
    case "unresolved":
      return `${UNRESOLVED_MEANING} ${range} Either the range includes zero or the typical ` +
        `(median) scenario points the other way from the average, so the direction is not ` +
        `established. This does not mean the two are equivalent.`;
    case "equivalent":
      return `${EQUIVALENT_MEANING} ${range} The whole range is inside the materiality threshold.`;
    case "alternative":
      return `${range} The alternative comes out ahead in the market scenarios.`;
    default:
      return `${range} The recommendation is ahead.`;
  }
}

/** When the winner and every alternative too close to call with it convert
 *  $0 this year, there is no year-0 spread to show -- what still separates
 *  them is WHEN each starts. Returns each one's start year (null = never), the
 *  winner first, or null when that is not the situation or the run predates
 *  first_conversion_year. */
export function closeStrategiesAllWait(
  alternatives: AlternativePolicy[],
  winningPolicyId: string,
  winnerYear0: number | undefined,
  winnerFirstYear: number | null | undefined,
): { policyId: string; firstYear: number | null }[] | null {
  if (winnerYear0 !== 0 || winnerFirstYear === undefined) return null;
  const close = alternatives.filter((a) => isCloseCall(a.paired?.verdict));
  if (close.length === 0) return null;
  if (close.some((a) => a.year0_conversion !== 0 || a.first_conversion_year === undefined)) {
    return null;
  }
  const rows = [
    { policyId: winningPolicyId, firstYear: winnerFirstYear },
    ...close.map((a) => ({ policyId: a.policy_id, firstYear: a.first_conversion_year ?? null })),
  ];
  // All never converting is "no conversions" all round: nothing to point at.
  return rows.some((r) => r.firstYear != null) ? rows : null;
}

function DeltaCell({
  value,
  betterWhenPositive,
  format,
}: {
  value: number;
  betterWhenPositive: boolean;
  format: "currency" | "percent";
}) {
  const better = value === 0 ? null : value > 0 === betterWhenPositive;
  const cls =
    better === null
      ? "text-muted-foreground"
      : better
        ? "text-secondary font-medium"
        : "text-destructive/80";
  const prefix = value > 0 ? "+" : "";
  const text =
    format === "percent"
      ? `${prefix}${(value * 100).toFixed(1)}%`
      : `${prefix}${formatCurrency(value)}`;
  return <span className={`tabular-nums ${cls}`}>{text}</span>;
}

/** Success is shown as each strategy's ABSOLUTE probability (winner + delta),
 *  because a delta of "0.0%" for a probability reads like "0% success". The
 *  colour still conveys direction vs the winner. */
function SuccessCell({
  deltaValue,
  winnerProbability,
}: {
  deltaValue: number;
  winnerProbability: number;
}) {
  const absolute = winnerProbability + deltaValue;
  // Colour by what the reader can see: two shares that both read "98%" are
  // not shown as better or worse on an unrounded difference.
  const shown = Math.round(absolute * 100) - Math.round(winnerProbability * 100);
  const cls =
    shown === 0
      ? "text-muted-foreground"
      : shown > 0
        ? "text-secondary font-medium"
        : "text-destructive/80";
  return (
    <span className={`tabular-nums ${cls}`}>
      {Math.round(absolute * 100)}%
    </span>
  );
}

function signedMoney(v: number): string {
  if (Math.abs(v) < 0.5) return "$0";
  return `${v > 0 ? "+" : "−"}${formatCurrency(Math.abs(v))}`;
}

const TAG = "ml-2 inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium";

/** The strategy cell both tables share: name, claim ages, and tags. */
function StrategyName({
  policyId, ages, optimizerPick, start,
}: { policyId: string; ages?: string | null; optimizerPick?: boolean; start?: number | null }) {
  return (
    <>
      <span className="font-medium">{policyLabel(policyId, start)}</span>
      {/* Joint claim-age runs: one strategy can appear at several ages. */}
      {ages && (
        <span className="ml-2 text-xs text-muted-foreground" data-testid="alt-claim-ages">
          claim at {ages}
        </span>
      )}
      {optimizerPick && (
        <span data-testid="optimizer-pick-tag" className={`${TAG} border-secondary/40 bg-secondary/10 text-secondary`}>
          optimizer&apos;s pick
        </span>
      )}
    </>
  );
}

function VerdictBadge({ paired }: { paired: NonNullable<AlternativePolicy["paired"]> }) {
  return (
    <span
      data-testid={`verdict-${paired.verdict}`}
      title={verdictExplanation(paired)}
      className={`${TAG} ml-0 ${
        isCloseCall(paired.verdict)
          ? "border-amber-300 bg-amber-50 text-amber-800"
          : "border-border bg-muted text-foreground/80"
      }`}
    >
      {VERDICT_LABEL[paired.verdict]}
    </span>
  );
}

const agesOf = (a: AlternativePolicy) =>
  a.key
    ? [
        a.claim_age_self != null ? `You ${a.claim_age_self}` : null,
        a.claim_age_spouse != null ? `Spouse ${a.claim_age_spouse}` : null,
      ].filter(Boolean).join(" · ")
    : null;

/**
 * The runners-up from the optimizer's policy search. With a market
 * simulation the main table ranks them as the optimizer did, on the modeled
 * score across the scenarios; the steady-return tax and estate deltas sit in
 * a disclosure, because on their own they can make a lower-ranked strategy
 * look better. Every row comes from a COMPLETE simulation of the full horizon.
 */
export function AlternativesTable({
  alternatives: given,
  winningPolicyId,
  winnerSuccessProbability,
  monteCarloRuns,
  firstYear,
  winnerYear0Conversion,
  optimizerPickId,
  winnerFirstConversionYear,
  ranking,
  closeCall,
  steadyReturn,
  startTraditional,
  materiality,
}: AlternativesTableProps) {
  if (given.length === 0) return null;
  // Without a market simulation a "paired comparison" rests on one path: no
  // labels, and no notes that depend on them.
  const simulated = monteCarloRuns !== 0;
  const alternatives = simulated ? given : given.map((a) => ({ ...a, paired: undefined }));
  const spread = year0Spread(alternatives, winnerYear0Conversion);
  const allWait = closeStrategiesAllWait(
    alternatives,
    winningPolicyId,
    winnerYear0Conversion,
    winnerFirstConversionYear,
  );
  const ranked = simulated && ranking && ranking.length > 0 ? ranking : null;
  const byKey = new Map(alternatives.map((a) => [a.key ?? a.policy_id, a]));
  // A conversion column of nothing but $0 says nothing the summary has not.
  const showConversion = !ranked || ranked.some((r) => (r.year0 ?? 0) > 0);
  const planWord = optimizerPickId ? "the plan you chose to run" : "the recommendation";
  const steadyTitle = `Compare taxes and estate assuming a steady ${
    steadyReturn != null ? `${pct(steadyReturn)} ` : ""
  }return`;

  const steadyTable = (
    <table className="w-full text-sm" data-testid={ranked ? "steady-table" : undefined}>
      <thead>
        <tr className="bg-muted/50 border-y border-border">
          <th className="px-6 py-2 text-left font-medium">Strategy</th>
          <th className="px-3 py-2 text-right font-medium">Tax difference · today&apos;s dollars</th>
          <th className="px-3 py-2 text-right font-medium">Estate difference</th>
          {!ranked && (
            <>
              <th className="px-3 py-2 text-right font-medium">Scenarios with spending funded</th>
              <th
                className="px-3 py-2 text-right font-medium"
                title={conversionTitle(firstYear)}
                data-testid="conversion-column"
              >
                {conversionHeading(firstYear)}
              </th>
            </>
          )}
        </tr>
      </thead>
      <tbody>
        {alternatives.map((a) => (
          <tr key={a.key ?? a.policy_id} className="border-b border-border/60 last:border-0">
            <td className="px-6 py-2.5">
              <StrategyName start={startTraditional} policyId={a.policy_id} ages={agesOf(a)}
                            optimizerPick={optimizerPickId === a.policy_id} />
              {/* The columns to the right come from ONE expected-return
                  scenario; the badge compares all scenarios path by path. */}
              {!ranked && a.paired && <span className="ml-2"><VerdictBadge paired={a.paired} /></span>}
            </td>
            <td className="px-3 py-2.5 text-right">
              {/* negative taxes delta = alternative pays LESS = better */}
              <DeltaCell value={a.lifetime_taxes_delta} betterWhenPositive={false} format="currency" />
            </td>
            <td className="px-3 py-2.5 text-right">
              <DeltaCell value={a.terminal_estate_delta} betterWhenPositive={true} format="currency" />
            </td>
            {!ranked && (
              <>
                <td className="px-3 py-2.5 text-right">
                  {/* No simulation: the one expected-return path is not a share. */}
                  {monteCarloRuns === 0 ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <SuccessCell deltaValue={a.success_probability_delta}
                                 winnerProbability={winnerSuccessProbability} />
                  )}
                </td>
                {/* Absolute, not a delta: what THIS strategy converts now. */}
                <td className="px-3 py-2.5 text-right tabular-nums" data-testid={`year0-cell-${a.policy_id}`}>
                  {a.year0_conversion != null ? formatCurrency(a.year0_conversion) : "—"}
                </td>
              </>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <div
      className="rounded-xl border border-border bg-card shadow-folio overflow-hidden"
      data-testid="alternatives-table"
    >
      <div className="px-6 pt-5 pb-3">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-primary">
          <span className="inline-block w-1 h-5 rounded-full bg-accent" aria-hidden="true" />
          Close alternatives
        </h2>
        {ranked ? (
          <p className="text-sm text-muted-foreground mt-1">
            Each strategy&apos;s modeled score — the after-tax estate minus spending-shortfall penalties,
            averaged across the same {ranked[0].scenarios} market scenarios in today&apos;s
            dollars. This is the measurement that ranked them, so it is the one to compare with{" "}
            {optimizerPickId ? (
              <>
                {planWord},{" "}
                <span className="font-medium text-foreground">{policyLabel(winningPolicyId, startTraditional)}</span>
              </>
            ) : (
              planWord
            )}
            .
          </p>
        ) : (
          <p className="text-sm text-muted-foreground mt-1">
            Compare these alternatives with{" "}
            {optimizerPickId ? (
              <>
                {planWord},{" "}
                <span className="font-medium text-foreground">{policyLabel(winningPolicyId, startTraditional)}</span>
              </>
            ) : (
              planWord
            )}
            . Negative tax amounts mean less tax; positive estate amounts mean more left to
            heirs. The conversion column shows the amount to convert, not a difference.
          </p>
        )}
        {ranked && closeCall && (
          <p
            data-testid="close-call"
            className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          >
            {closeCall}
          </p>
        )}
        {monteCarloRuns !== 0 && <VerdictLegend materiality={materiality} />}
        <details className="mt-2 text-sm text-muted-foreground" data-testid="comparisons-explainer">
          <summary className="cursor-pointer font-medium text-primary">How these comparisons work</summary>
          <div className="mt-2 space-y-2">
            {monteCarloRuns === 0 ? (
              <p>
                The market simulation was skipped for this run, so the recommendation was chosen
                on the steady-return projection the tax and estate differences come from.
              </p>
            ) : ranked ? (
              <>
                <p>
                  Every strategy faces the same market scenarios. The difference column is each
                  strategy&apos;s average score minus the score of {planWord}, so a negative
                  amount means it scored lower on average.
                </p>
                <p>
                  The taxes and estate under “{steadyTitle}” come from the steady-return
                  projection, where every year earns the same return. A strategy can pay less tax
                  or leave more estate there and still rank lower, because the ranking reflects
                  how each strategy holds up when returns vary.
                </p>
              </>
            ) : (
              <>
                <p>
                  Tax and estate differences come from the steady-return projection. The share
                  of scenarios with spending funded is each strategy&apos;s own (green or red when
                  higher or lower than the recommendation&apos;s).
                </p>
                <p>
                  The recommendation is chosen by its modeled score across{" "}
                  {monteCarloRuns ? `${monteCarloRuns} ` : ""}market scenarios, not on the
                  steady-return figures shown here. In a plan with real risk of running short, a
                  strategy can look better on these figures yet rank below a recommendation that
                  holds up better when markets do badly.
                </p>
              </>
            )}
          </div>
        </details>
        {spread && winnerYear0Conversion != null && (
          <p
            data-testid="year0-spread"
            className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          >
            <span className="font-medium">
              The {firstYear != null ? `${firstYear} ` : ""}amount is not settled.
            </span>{" "}
            The recommendation converts {formatCurrency(winnerYear0Conversion)}{" "}
            {firstYear != null ? `in ${firstYear}` : "this year"}, but the strategies the simulation cannot distinguish from it convert anywhere
            from {formatCurrency(spread.low)} to {formatCurrency(spread.high)}.
            Treat it as a range: compare them on the What-if page before acting.
          </p>
        )}
        {allWait && (
          <div
            data-testid="year0-all-wait"
            className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          >
            <p>
              <span className="font-medium">
                No Roth conversion {firstYear != null ? `in ${firstYear}` : "this year"}.
              </span>{" "}
              The recommendation and the strategies the simulation cannot distinguish from it differ in
              when they start converting, but none of them converts anything
              {firstYear != null ? ` in ${firstYear}` : " this year"}. Re-run next year with your real balances.
            </p>
            <ul className="mt-1 list-disc pl-5">
              {allWait.map((r) => (
                <li key={r.policyId}>
                  {policyLabel(r.policyId, startTraditional)}: {r.firstYear != null ? `from ${r.firstYear}` : "never"}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        {ranked ? (
          <table className="w-full text-sm" data-testid="ranking-table">
            <thead>
              <tr className="bg-muted/50 border-y border-border">
                <th className="px-6 py-2 text-left font-medium">Strategy</th>
                <th className="px-3 py-2 text-right font-medium">Average modeled score</th>
                <th className="px-3 py-2 text-right font-medium">
                  Difference from {optimizerPickId ? "the plan you ran" : "recommendation"}
                </th>
                <th className="px-3 py-2 text-right font-medium">Scenarios with spending funded</th>
                <th className="px-3 py-2 text-left font-medium">Comparison result</th>
                {showConversion && (
                  <th
                    className="px-3 py-2 text-right font-medium"
                    title={conversionTitle(firstYear)}
                    data-testid="conversion-column"
                  >
                    {conversionHeading(firstYear)}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {ranked.map((r, i) => {
                const alt = byKey.get(r.key);
                return (
                  <tr
                    key={r.key}
                    className={`border-b border-border/60 last:border-0 ${r.isRecommendation ? "bg-secondary/5" : ""}`}
                    data-testid={r.isRecommendation ? "ranking-recommendation" : `ranking-row-${r.key}`}
                  >
                    <td className="px-6 py-2.5">
                      <StrategyName start={startTraditional} policyId={r.policyId} ages={r.ages}
                                    optimizerPick={!r.isRecommendation && optimizerPickId === r.policyId} />
                      {r.isRecommendation && (
                        <span className={`${TAG} border-secondary/40 bg-secondary/10 text-secondary`}>
                          {optimizerPickId ? "Plan you chose to run" : "Recommendation"}
                        </span>
                      )}
                      {r.isRecommendation && i === 0 && (
                        <span className="ml-2 text-xs text-muted-foreground">highest average score</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {r.score != null ? formatCurrency(r.score) : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {r.isRecommendation ? "—" : signedMoney(r.difference)}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {r.funded} of {r.scenarios}
                    </td>
                    <td className="px-3 py-2.5">
                      {alt?.paired ? <VerdictBadge paired={alt.paired} /> : "—"}
                    </td>
                    {showConversion && (
                      <td className="px-3 py-2.5 text-right tabular-nums" data-testid={`year0-cell-${r.policyId}`}>
                        {r.year0 != null ? formatCurrency(r.year0) : "—"}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          steadyTable
        )}
      </div>
      {ranked && ranked.some((r) => r.scenarios !== ranked[0].scenarios) && (
        <p className="px-6 py-2 text-xs text-muted-foreground border-t border-border/60" data-testid="fewer-scenarios">
          A strategy set aside early in the search was scored on fewer market scenarios, as its
          spending-funded count shows; its difference is measured on the scenarios both share.
        </p>
      )}
      {ranked && (
        <details className="border-t border-border/60" data-testid="steady-comparison">
          <summary className="cursor-pointer px-6 py-3 text-sm font-medium text-primary">{steadyTitle}</summary>
          <p className="px-6 pb-3 text-sm text-muted-foreground">
            One projection in which every year earns exactly{" "}
            {steadyReturn != null ? pct(steadyReturn) : "the assumed average return"}, compared
            with {planWord}. Negative tax amounts mean less tax; positive estate amounts mean more
            left to heirs. These figures did not decide the ranking above.
          </p>
          <div className="overflow-x-auto">{steadyTable}</div>
        </details>
      )}
      {(showConversion || usesRuleNames(winningPolicyId, alternatives)) && (
      <p className="px-6 py-3 text-xs text-muted-foreground border-t border-border/60">
        {showConversion && conversionTitle(firstYear)}
        {usesRuleNames(winningPolicyId, alternatives) && (
          <>
            {showConversion && " "}
            <em>Every year</em> applies the same rule every year until the IRA is exhausted;{" "}
            <em>through YYYY</em> applies it through that year, then stops;{" "}
            {startTraditional != null ? (
              <>
                <em>up to $N annually</em> converts one fixed amount each year: 5%, 10% or 20% of
                the traditional balance at the start, computed once
              </>
            ) : (
              <>
                <em>up to N% of the starting IRA</em> converts one fixed dollar amount each year
              </>
            )}{" "}
            (less, or nothing, in a year when a cap, the year&apos;s spending or a Medicare
            surcharge setting allows less, so the years it actually converts can differ).
          </>
        )}
      </p>
      )}
    </div>
  );
}
