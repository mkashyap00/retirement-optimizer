/** What a run's market scenarios and its steady-return projection assumed,
 *  from the run's own record. Older runs did not record the model; their
 *  average return comes from the inputs snapshot and the volatility is
 *  left unstated rather than assumed. */

import type { OptimizationResult } from "@/lib/types";

export interface MarketFacts {
  /** Market scenarios each strategy was finally scored on; 0 = none. */
  scenarios: number;
  /** Assumed average annual return, or null when unknown. */
  meanReturn: number | null;
  /** Standard deviation of annual returns, or null when not recorded. */
  volatility: number | null;
}

export function marketFacts(r: OptimizationResult, nominalReturn?: number | null): MarketFacts {
  const m = r.market_model;
  return {
    scenarios: r.monte_carlo_runs ?? 0,
    meanReturn: m?.mean_return ?? nominalReturn ?? null,
    volatility: m?.volatility ?? null,
  };
}

/** 0.06 → "6%", 0.065 → "6.5%". */
export function pct(x: number): string {
  return `${Math.round(x * 1000) / 10}%`;
}

/** The short label used wherever a figure comes from the steady-return
 *  projection; it is defined once, in the market explanation. */
export const STEADY_LABEL = "Steady-return projection";

/** "Projection assuming a steady 6% annual return". */
export function steadyDefinition(meanReturn: number | null): string {
  return meanReturn != null
    ? `Projection assuming a steady ${pct(meanReturn)} annual return`
    : "Projection assuming a steady annual return at your assumed rate";
}
