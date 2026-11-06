"use client";

import React, { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { YearRow } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { RationalePanel } from "./RationalePanel";
import { SalePlanInline } from "./SalePlanInline";
import { narrativeFor } from "@/lib/zeroConversion";

interface YearTableProps {
  rows: YearRow[];
  /** Plan-to ages; a person's age column goes blank once past their own. */
  selfDeathAge?: number | null;
  spouseDeathAge?: number | null;
  /** The plan's strategy: restates older runs' either/or zero-conversion
   *  sentence with the known reason. */
  policyId?: string;
}

/**
 * Portion of this year's taxable withdrawal that funds Roth conversion
 * taxes: total tax minus the rationale's no-conversion counterfactual,
 * capped at the withdrawal itself. 0 for non-conversion years.
 */
function conversionTaxPortion(row: YearRow): number {
  const counterfactual = row.rationale?.conversion?.counterfactual_none_tax;
  if (!(row.conversion > 0) || counterfactual == null) return 0;
  return Math.max(
    0,
    Math.min(row.withdrawal_taxable, row.total_tax - counterfactual)
  );
}

// Compact currency for the Funded-by cell: $40k / $1.2M
function fmtCompact(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${Math.round(v / 1_000)}k`;
  return `$${Math.round(v)}`;
}

/**
 * Where the year's spending money came from: mini stacked bar + labels.
 * Colors match the balances chart (gold=taxable, emerald=traditional,
 * teal=Roth — see chartTheme.ts).
 */
function FundedBy({ row }: { row: YearRow }) {
  const parts = [
    { label: "Taxable", value: row.withdrawal_taxable, color: "#b9942f" },
    { label: "IRA", value: row.withdrawal_traditional, color: "#064e3b" },
    { label: "Roth", value: row.withdrawal_roth, color: "#0d9488" },
  ].filter((p) => p.value > 0);

  if (parts.length === 0) {
    return <span className="text-muted-foreground">—</span>;
  }

  const total = parts.reduce((s, p) => s + p.value, 0);

  return (
    <div className="min-w-[7rem]" data-testid={`funded-by-${row.year}`}>
      <div className="flex h-1.5 w-full rounded-full overflow-hidden bg-muted/60 mb-1">
        {parts.map((p) => (
          <span
            key={p.label}
            style={{ width: `${(p.value / total) * 100}%`, backgroundColor: p.color }}
          />
        ))}
      </div>
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {parts.map((p) => `${p.label} ${fmtCompact(p.value)}`).join(" · ")}
      </span>
    </div>
  );
}

/**
 * Room left in the bracket the year's ordinary income lands in — what a
 * further Roth conversion could use before the next rate applies. "—" in the
 * top bracket (no ceiling) and on rows stored without bracket facts. Mirrors
 * backend/src/reports/display.py bracket_room — keep in sync.
 */
function BracketRoom({ row }: { row: YearRow }) {
  const bracket = row.rationale?.bracket;
  if (!bracket || bracket.bracket_top == null) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <>
      {formatCurrency(bracket.headroom_remaining)}
      <span className="block text-xs text-muted-foreground">
        left in {Math.round(bracket.bracket_rate * 100)}%
      </span>
    </>
  );
}

export function YearTable({
  rows,
  selfDeathAge,
  spouseDeathAge,
  policyId,
}: YearTableProps) {
  const [expandedYear, setExpandedYear] = useState<number | null>(null);
  const hasSpouseAge = rows.some((r) => r.age_spouse != null);

  // Sale planning is annual-cadence: only the FIRST year that draws on the
  // taxable account is actionable. Every year is priced against today's
  // holdings, so a later year's sell list would be a near-duplicate — you
  // re-run the plan next year with a fresh portfolio instead. We offer the
  // inline planner on that first year only and note the rest.
  const firstSaleYear =
    rows.find((r) => r.withdrawal_taxable > 0)?.year ?? null;

  function toggleRow(year: number) {
    setExpandedYear((prev) => (prev === year ? null : year));
  }

  // The household simulates to the LONGER spouse horizon; a person's age
  // column goes blank once past their own plan-to age. Mirrors
  // backend/src/reports/display.py — keep in sync.
  function ageCell(age: number | null | undefined, deathAge?: number | null) {
    if (age == null) return "—";
    if (deathAge != null && age > deathAge) return "—";
    return age;
  }

  return (
    <div className="rounded-xl border border-border bg-card overflow-x-auto shadow-folio">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-primary text-primary-foreground">
            <th className="px-3 py-2.5 text-left font-medium">
              Year <span className="sr-only">(select to see why)</span>
            </th>
            <th className="px-3 py-2.5 text-left font-medium">Age</th>
            {hasSpouseAge && (
              <th className="px-3 py-2.5 text-left font-medium">Spouse Age</th>
            )}
            <th className="px-3 py-2.5 text-right font-medium">Conversion</th>
            <th className="px-3 py-2.5 text-right font-medium">RMD</th>
            <th className="px-3 py-2.5 text-left font-medium">Funded By</th>
            <th className="px-3 py-2.5 text-right font-medium">Total Tax</th>
            <th className="px-3 py-2.5 text-right font-medium">Marginal %</th>
            <th
              className="px-3 py-2.5 text-right font-medium"
              title={
                "Ordinary income that still fits in the bracket this year " +
                "lands in. Marginal % is the rate on the next dollar, so a " +
                "year filled to a bracket's edge shows the next bracket there."
              }
            >
              Bracket Room
            </th>
            <th className="px-3 py-2.5 text-right font-medium">Net Spendable</th>
            <th className="px-3 py-2.5 text-right font-medium">Total Balance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const totalBalance =
              row.balance_taxable + row.balance_traditional + row.balance_roth;
            const isExpanded = expandedYear === row.year;
            // The plan now runs to the full horizon even when the money runs
            // out, so a row can show less spendable cash than the plan needs.
            // Saying so on the row is the whole point of simulating it.
            const shortfall = row.shortfall ?? 0;
            // Spending the guardrails gave up. Distinct from a shortfall: the
            // plan CHOSE this, and it is still lost consumption, so the row has
            // to show it rather than quietly lowering the bar it is judged by.
            const cut = row.discretionary_cut ?? 0;
            return (
              <React.Fragment key={row.year}>
                <tr
                  className={`border-b border-border/70 cursor-pointer transition-colors ${
                    isExpanded ? "bg-accent/10" : "hover:bg-accent/[0.06]"
                  }`}
                  onClick={() => toggleRow(row.year)}
                  data-testid={`year-row-${row.year}`}
                >
                  <td className="px-3 py-2 font-medium">
                    {/* The visible, keyboard-reachable control; the whole row
                        stays clickable for the mouse. */}
                    <button
                      type="button"
                      aria-expanded={isExpanded}
                      aria-controls={`rationale-${row.year}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleRow(row.year);
                      }}
                      className="inline-flex items-center gap-1 rounded px-1 -mx-1 hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                      data-testid={`year-toggle-${row.year}`}
                    >
                      <ChevronRight
                        className={`h-4 w-4 text-muted-foreground transition-transform ${isExpanded ? "rotate-90" : ""}`}
                        aria-hidden="true"
                      />
                      {row.year}
                      <span className="sr-only">{isExpanded ? "hide" : "show"} why</span>
                    </button>
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {ageCell(row.age_self, selfDeathAge)}
                  </td>
                  {hasSpouseAge && (
                    <td className="px-3 py-2 tabular-nums">
                      {ageCell(row.age_spouse, spouseDeathAge)}
                    </td>
                  )}
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.conversion > 0 ? (
                      <span className="font-semibold text-accent-foreground bg-accent/20 rounded px-1.5 py-0.5">
                        {formatCurrency(row.conversion)}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.rmd > 0 ? formatCurrency(row.rmd) : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2">
                    <FundedBy row={row} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(row.total_tax)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatPercent(row.marginal_rate * 100)}
                  </td>
                  <td
                    className="px-3 py-2 text-right tabular-nums"
                    data-testid={`bracket-room-${row.year}`}
                  >
                    <BracketRoom row={row} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {shortfall > 0 ? (
                      <span
                        data-testid={`shortfall-${row.year}`}
                        title={
                          `Underfunded: this year needs ` +
                          `${formatCurrency(row.required_spending)} but only ` +
                          `${formatCurrency(row.net_spendable)} is available ` +
                          `after tax, with every account already drawn down.`
                        }
                      >
                        <span className="text-destructive font-medium">
                          {formatCurrency(row.net_spendable)}
                        </span>
                        <span className="block text-xs text-destructive/80">
                          {formatCurrency(shortfall)} short
                        </span>
                      </span>
                    ) : cut > 0 ? (
                      <span
                        data-testid={`spending-cut-${row.year}`}
                        title={
                          `Guardrails reduced this year's spending. Your target ` +
                          `was ${formatCurrency(row.target_spending ?? 0)}; the ` +
                          `plan spends ${formatCurrency(row.required_spending)} ` +
                          `to protect the portfolio. The optimizer charges this ` +
                          `as a real loss, at half the weight of spending you ` +
                          `cannot fund at all.`
                        }
                      >
                        {formatCurrency(row.net_spendable)}
                        <span className="block text-xs text-amber-700 dark:text-amber-500">
                          {formatCurrency(cut)} below target
                        </span>
                      </span>
                    ) : (
                      formatCurrency(row.net_spendable)
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium text-primary">
                    {formatCurrency(totalBalance)}
                  </td>
                </tr>
                {isExpanded && (
                  <tr key={`rationale-${row.year}`} id={`rationale-${row.year}`}>
                    <td colSpan={hasSpouseAge ? 11 : 10} className="px-3 py-2">
                      <RationalePanel
                        rationale={{ ...row.rationale, narrative: narrativeFor(row, rows, policyId) }}
                      />
                      {row.withdrawal_taxable > 0 &&
                        row.year === firstSaleYear &&
                        (() => {
                          const cash = Math.round(row.withdrawal_taxable);
                          const convTax = Math.round(conversionTaxPortion(row));
                          const spend = cash - convTax;
                          return (
                            <div data-testid={`sale-link-${row.year}`}>
                              <SalePlanInline
                                cash={cash}
                                spend={spend}
                                convTax={convTax}
                              />
                            </div>
                          );
                        })()}
                      {row.withdrawal_taxable > 0 &&
                        row.year !== firstSaleYear && (
                          <p
                            className="mt-2 text-xs text-muted-foreground"
                            data-testid={`sale-note-${row.year}`}
                          >
                            Sell lists are planned one year at a time. Re-run
                            this plan next year with your updated portfolio to
                            plan {row.year}&apos;s sale.
                          </p>
                        )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
