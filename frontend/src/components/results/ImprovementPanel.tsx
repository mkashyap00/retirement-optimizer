"use client";

import type { OptimizationResult } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import {
  VERDICT_LABEL,
  improvementSummary,
  simulated,
  type Improvement,
} from "@/lib/resultSummary";

function signedCurrency(v: number): string {
  if (Math.abs(v) < 0.5) return "$0";
  return `${v > 0 ? "+" : "−"}${formatCurrency(Math.abs(v))}`;
}

function signedCount(v: number): string {
  return v === 0 ? "no change" : `${v > 0 ? "+" : "−"}${Math.abs(v)}`;
}

/** One "from → to" comparison: both outcomes and the difference. */
function ComparisonTable({ c, sim }: { c: Improvement; sim: boolean }) {
  const label = (what: string) => (sim ? `Average ${what}` : what[0].toUpperCase() + what.slice(1));
  const money = (label: string, from: number | null, to: number | null, testid: string) =>
    from == null || to == null ? null : (
      <tr className="border-b border-border/60" data-testid={testid}>
        <th scope="row" className="py-2 pr-4 text-left font-normal">{label}</th>
        <td className="py-2 pr-4 text-right tabular-nums">{formatCurrency(from)}</td>
        <td className="py-2 pr-4 text-right tabular-nums">{formatCurrency(to)}</td>
        <td className="py-2 text-right tabular-nums font-semibold">{signedCurrency(to - from)}</td>
      </tr>
    );
  const { from, to } = c;
  return (
    <div className="space-y-2" data-testid={`improvement-${c.id}`}>
      <h3 className="font-semibold text-foreground">{c.title}</h3>
      <p className="text-sm" data-testid={`improvement-${c.id}-sentence`}>{c.sentence}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-muted-foreground border-b border-border">
              <th className="py-2 pr-4 text-left font-medium">
                {sim ? `Across the same ${to.scenarios} market scenarios` : "Steady-return projection"}
              </th>
              <th className="py-2 pr-4 text-right font-medium">{from.label}</th>
              <th className="py-2 pr-4 text-right font-medium">{to.label}</th>
              <th className="py-2 text-right font-medium">Difference</th>
            </tr>
          </thead>
          <tbody>
            {money(label("modeled score"), from.score, to.score, "row-score")}
            {money(label("after-tax estate"), from.estate, to.estate, "row-estate")}
            {money(label("unfunded spending"), from.unfunded, to.unfunded, "row-unfunded")}
            {from.funded != null && to.funded != null && (
              <tr className="border-b border-border/60" data-testid="row-funded">
                <th scope="row" className="py-2 pr-4 text-left font-normal">Scenarios with spending funded</th>
                <td className="py-2 pr-4 text-right tabular-nums">{from.funded} of {from.scenarios}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{to.funded} of {to.scenarios}</td>
                <td className="py-2 text-right tabular-nums font-semibold">{signedCount(to.funded - from.funded)}</td>
              </tr>
            )}
            {c.verdict && (
              <tr data-testid="row-verdict">
                <th scope="row" className="py-2 pr-4 text-left font-normal">Comparison result</th>
                <td colSpan={3} className="py-2 text-right">{VERDICT_LABEL[c.verdict]}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The recommendation against the user's own choices, as explicit
 *  "from → to" comparisons with both outcomes shown. The comparisons overlap:
 *  never add them. With nothing to compare, only quiet notes remain. */
export function ImprovementPanel({ result }: { result: OptimizationResult }) {
  const { comparisons, notes } = improvementSummary(result);
  if (comparisons.length === 0) {
    if (notes.length === 0) return null;
    return (
      <div className="space-y-1" data-testid="improvement-notes">
        {notes.map((n) => (
          <p key={n} className="text-sm text-muted-foreground" data-testid="improvement-note">{n}</p>
        ))}
      </div>
    );
  }
  const sim = simulated(result);
  const paths = sim ? (result.winning_policy.monte_carlo_paths ?? result.monte_carlo_runs) : 0;
  return (
    <section
      className="rounded-xl border border-border bg-card shadow-folio px-6 py-5 space-y-4"
      data-testid="improvement-panel"
    >
      <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-primary">
        <span className="inline-block w-1 h-5 rounded-full bg-accent" aria-hidden="true" />
        Recommended strategy compared with your original choices
      </h2>
      {comparisons.map((c) => <ComparisonTable key={c.id} c={c} sim={sim} />)}
      {notes.map((n) => (
        <p key={n} className="text-sm" data-testid="improvement-note">{n}</p>
      ))}
      <p className="text-sm text-muted-foreground">
        The modeled score is the after-tax estate minus spending-shortfall penalties,
        {paths
          ? ` averaged across the same ${paths} market scenarios`
          : " on the steady-return projection"}
        , in today&apos;s dollars. A higher score is neither tax saved nor a guaranteed
        increase in your estate.
        {comparisons.length > 1 &&
          " Each comparison answers a different question about the same recommendation, so do not add the differences together."}
        {!sim && " No market simulation ran, so there is no comparison result."}
      </p>
    </section>
  );
}
