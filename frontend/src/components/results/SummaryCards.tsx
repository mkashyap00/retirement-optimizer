"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { OptimizationResult, SpendingRule } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/utils";
import {
  claimSentence,
  confidenceSentence,
  conversionSentence,
  fixedAgesSentence,
  higherSuccessAlternative,
  longevityTradeoff,
  simulated,
} from "@/lib/resultSummary";
import { pct, STEADY_LABEL, steadyDefinition, type MarketFacts } from "@/lib/marketModel";

interface SummaryCardsProps {
  result: OptimizationResult;
  /** The plan's name, for the heading ("Sample plan — Recommended strategy"). */
  planName?: string | null;
  /** The run's spending rule, from its inputs snapshot: under "guardrails"
   *  some years below target are planned cuts. Unknown = say nothing. */
  spendingRule?: SpendingRule | null;
  /** The run's market model, for the explanation beneath the cards. */
  market?: MarketFacts;
}

/** The recommendation, how sure it is, and the four figures behind it --
 *  each labelled with what it measures: the expected-return projection, or
 *  the simulated market paths. */
export function SummaryCards({ result, planName, spendingRule, market }: SummaryCardsProps) {
  const { winning_policy: wp, monte_carlo_runs } = result;
  const joint = result.search?.mode === "joint" || result.search?.mode === "joint_deterministic";
  // A deterministic run stores its expected-return path as one "path":
  // whether markets were simulated is the run's setting, not the count.
  const paths = simulated(result) ? (wp.monte_carlo_paths ?? monte_carlo_runs) : 0;
  const forced = !!result.forced_policy;

  const claimLine = joint
    ? claimSentence(wp.claim_age_self, wp.claim_age_spouse)
    : fixedAgesSentence(result.claim_ages?.self, result.claim_ages?.spouse);
  const eyebrow = forced
    ? "Strategy you chose to run"
    : joint
      ? "Recommended strategy"
      : "Conversion optimization · recommended strategy";
  const confidence = confidenceSentence(result);
  const safer = forced ? null : higherSuccessAlternative(result);

  // Today's-dollar estate from whichever expected-return breakdown the run has.
  const det =
    wp.deterministic_score_components ??
    (wp.score_components?.basis === "deterministic" ? wp.score_components : undefined);

  const cards: {
    label: string; value: string; hint?: string; basis?: string; note?: string; testid: string;
  }[] = [
    {
      label: "Spending funded in market scenarios",
      testid: "card-success",
      // Whole points with the interval: the decimal place was noise.
      value: paths ? `${Math.round(wp.success_probability * 100)}%` : "—",
      hint: (() => {
        if (!paths) return "No market simulation";
        const p = wp.success_probability;
        const half = 1.96 * Math.sqrt((p * (1 - p)) / paths);
        return `± ${Math.round(half * 100)} pts (${paths} scenarios)`;
      })(),
      // Neutral: the count includes years savings could not fund, with or
      // without guardrails. The planned-cut explanation is separate.
      note: (() => {
        const yrs = wp.mean_years_reduced;
        if (!paths || !yrs || yrs <= 0) return undefined;
        const rounded = yrs < 1 ? yrs.toFixed(1) : Math.round(yrs).toString();
        return `Spending below target in approximately ${rounded} year${
          rounded === "1" ? "" : "s"
        } per market scenario.`;
      })(),
    },
    {
      label: "Modeled score",
      testid: "card-score",
      value: formatCurrency(wp.score),
      hint: `${paths ? "Average after-tax" : "After-tax"} estate minus spending-shortfall penalties.`,
      basis: `Today's dollars · ${paths ? `${paths} market scenarios` : STEADY_LABEL.toLowerCase()}`,
    },
    {
      label: `Projected estate at a steady ${
        market?.meanReturn != null ? `${pct(market.meanReturn)} ` : ""
      }annual return`,
      testid: "card-estate",
      value: formatCurrency(wp.terminal_estate),
      hint: "At the end of your plan",
      basis: det ? `Equivalent to ${formatCurrency(det.terminal_estate_pv)} today` : undefined,
    },
    {
      label: `Lifetime taxes — ${STEADY_LABEL.toLowerCase()}`,
      testid: "card-taxes",
      value: formatCurrency(wp.lifetime_taxes_nominal),
      hint: `${formatCurrency(wp.lifetime_taxes_pv)} in today's dollars (${
        Math.round((wp.discount_rate ?? 0.02) * 1000) / 10
      }% discount)`,
    },
  ];

  return (
    <div className="space-y-4">
      <div
        data-testid="winning-policy-banner"
        className="relative overflow-hidden rounded-xl bg-primary text-primary-foreground shadow-folio pl-6 pr-5 py-5 space-y-1.5"
      >
        <span className="absolute inset-y-0 left-0 w-1.5 bg-accent" aria-hidden="true" />
        <p className="text-xs font-medium uppercase tracking-wide text-primary-foreground/70">
          {planName ? `${planName} — ` : ""}
          {eyebrow}
        </p>
        {claimLine && (
          <p data-testid="recommendation-claim" className="font-display text-xl font-bold sm:text-2xl">
            {claimLine}
          </p>
        )}
        <p
          data-testid="recommendation-conversion"
          className={claimLine ? "text-base font-medium" : "font-display text-xl font-bold sm:text-2xl"}
        >
          {conversionSentence(result)}
        </p>
        {confidence && (
          <p data-testid="recommendation-confidence" className="text-sm text-primary-foreground/80">
            {confidence}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {cards.map(({ label, value, hint, basis, note, testid }) => (
          <Card key={label} data-testid={testid} className="relative overflow-hidden shadow-folio border-border">
            <span className="absolute inset-x-0 top-0 h-0.5 bg-accent" aria-hidden="true" />
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="font-display text-2xl font-bold text-primary tabular-nums">{value}</p>
              {hint && (
                <p data-testid="card-hint" className="mt-0.5 text-sm text-muted-foreground tabular-nums">
                  {hint}
                </p>
              )}
              {basis && (
                <p data-testid="card-basis" className="text-sm text-muted-foreground tabular-nums">
                  {basis}
                </p>
              )}
              {note && (
                <p data-testid="card-note" className="mt-1 text-sm text-muted-foreground">
                  {note}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {market && <MarketExplanation market={market} />}

      {paths > 0 && spendingRule === "guardrails" && (wp.mean_years_reduced ?? 0) > 0 && (
        <p data-testid="guardrail-note" className="text-sm text-muted-foreground">
          Guardrails are on: after weak markets the plan cuts spending on purpose, so the years
          below target include these planned cuts as well as any years savings could not fund
          the target.
        </p>
      )}

      {!forced && longevityTradeoff(result) && (
        <p data-testid="longevity-tradeoff" className="text-sm text-muted-foreground">
          {longevityTradeoff(result)}
        </p>
      )}

      {safer && (
        <p data-testid="success-tradeoff" className="text-sm text-muted-foreground">
          An alternative funds spending in more market scenarios (
          {Math.round((wp.success_probability + safer.success_probability_delta) * 100)}% against{" "}
          {Math.round(wp.success_probability * 100)}%). The recommendation is ranked on the
          modeled score, which weighs the estate it leaves against any spending it cannot fund —
          not on that share alone.
        </p>
      )}

      <details className="rounded-lg border border-border bg-card px-4 py-3 text-sm" data-testid="score-explainer">
        <summary className="cursor-pointer font-medium text-primary">How the modeled score is built</summary>
        <div className="mt-2 space-y-2 text-muted-foreground">
          {wp.score_components && <ScoreLine c={wp.score_components} />}
          <p>
            Highest marginal tax rate projected without conversions ({STEADY_LABEL.toLowerCase()}):{" "}
            {formatPercent(wp.projected_future_marginal_rate * 100)} — the rate converting
            now is weighed against.
          </p>
        </div>
      </details>
    </div>
  );
}

/** "Claim Social Security at 70 (you) and 67 (spouse)". */
export function claimAgesText(self?: number | null, spouse?: number | null): string {
  const parts = [
    self != null ? `${self} (you)` : null,
    spouse != null ? `${spouse} (spouse)` : null,
  ].filter(Boolean);
  return parts.length ? `Claim Social Security at ${parts.join(" and ")}` : "";
}

/** One sentence stating what the score is made of, in today's dollars.
 *  basis "deterministic": the expected-return path's figures (the Monte Carlo
 *  score averages the same objective over every scenario). basis
 *  "monte_carlo" (joint claim-age runs): means over the scored scenarios, so
 *  they add up to the score shown. */
function ScoreLine({ c }: { c: NonNullable<OptimizationResult["winning_policy"]["score_components"]> }) {
  const mc = c.basis === "monte_carlo";
  const parts = [`after-tax estate ${formatCurrency(mc ? c.estate_pv : c.terminal_estate_pv)}`];
  if (c.shortfall_pv > 0) {
    parts.push(
      `minus unfunded essential spending ${formatCurrency(c.shortfall_pv)}${
        c.shortfall_weight !== 1 ? ` × ${c.shortfall_weight}` : ""
      }`,
    );
  }
  if (c.discretionary_shortfall_pv > 0) {
    parts.push(
      `minus spending cut above the floor ${formatCurrency(
        c.discretionary_shortfall_pv,
      )} × ${c.discretionary_shortfall_weight}`,
    );
  }
  return (
    <p data-testid="score-components">
      What the optimizer maximizes, in today&apos;s dollars{" "}
      {mc
        ? `averaged over ${c.monte_carlo_paths} market scenarios`
        : "on the steady-return projection"}
      : {parts.join(", ")} = {formatCurrency(mc ? c.score : c.deterministic_value)}.
      Lifetime taxes ({formatCurrency(c.lifetime_taxes_pv)}) are already out of
      the estate, so they are not subtracted again.
    </p>
  );
}

/** What the market scenarios are, where they first appear, with the run's
 *  own recorded assumptions; and the one definition of the steady-return
 *  projection the other labels refer to. */
export function MarketExplanation({ market }: { market: MarketFacts }) {
  const avg = market.meanReturn != null ? ` of ${pct(market.meanReturn)}` : "";
  const steady = `${steadyDefinition(market.meanReturn)} (labelled \u201c${STEADY_LABEL}\u201d).`;
  return (
    <section
      data-testid="market-explanation"
      className="rounded-lg border border-border bg-card px-4 py-3 text-sm space-y-1.5"
    >
      <h3 className="font-medium text-primary">
        {market.scenarios > 0 ? "How we simulate market outcomes" : "No market simulation"}
      </h3>
      {market.scenarios > 0 ? (
        <>
          <p className="text-muted-foreground">
            We use Monte Carlo simulation to test your plan under {market.scenarios} possible
            investment-return scenarios. Returns vary from year to year, including gains and
            losses, around your assumed average annual return{avg}. Every strategy faces the same
            market scenarios so the comparison is fair.
          </p>
          {market.volatility != null && (
            <p className="text-muted-foreground" data-testid="market-technical">
              Annual volatility is {Math.round(market.volatility * 1000) / 10} percentage points,
              measured as the standard deviation of annual returns. The model draws each
              year&apos;s return independently from a normal distribution.
            </p>
          )}
          <p className="text-muted-foreground">
            The estate, taxes, charts and year-by-year table use a {steady.charAt(0).toLowerCase()}
            {steady.slice(1)}
          </p>
        </>
      ) : (
        <p className="text-muted-foreground">
          This run did not simulate market outcomes. Every figure comes from a{" "}
          {steady.charAt(0).toLowerCase()}
          {steady.slice(1)} There is no measure of how the strategies fare when returns vary.
        </p>
      )}
    </section>
  );
}
