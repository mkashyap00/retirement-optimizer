"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import {
  listHouseholds,
  getHousehold,
  compareScenarios,
  listScenarioPolicies,
} from "@/lib/api";
import type {
  HouseholdSummary,
  CompareConstraints,
  CompareOverrides,
  CompareResult,
  ConversionWindow,
  IrmaaPolicy,
  OptimizationResult,
  SpendingRule,
} from "@/lib/types";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { policyLabel, strategyOptions } from "@/lib/policyLabels";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/utils";
import {
  SERIES,
  GRID_STROKE,
  AXIS_TICK,
  AXIS_LINE,
  TOOLTIP_STYLE,
} from "@/components/results/chartTheme";
import { describeDelta } from "@/lib/compareDelta";
import { recommendedClaimAges } from "@/lib/runs";
import { CurrencyInput } from "@/components/ui/currency-input";
import { changes, changeSummary, type FieldKey, type Scenario } from "@/lib/whatIfChanges";
import { BRACKET_CAP_OPTIONS, bracketCapSelectValue } from "@/lib/brackets";
import { IRMAA_CHOICES, irmaaChoice } from "@/lib/labels";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// ScenarioForm — local constraint editor for one scenario
// ---------------------------------------------------------------------------


const WINDOW_OPTIONS: { value: ConversionWindow; label: string }[] = [
  { value: "anytime", label: "Anytime" },
  { value: "pre_medicare", label: "Pre-Medicare" },
  { value: "pre_rmd", label: "Pre-RMD" },
  { value: "pre_ss", label: "Pre-Social Security" },
];

const CLAIM_AGES = [62, 63, 64, 65, 66, 67, 68, 69, 70];
const NO_DEATH = "none";
// Coarse on purpose. A finer grid would imply the year is knowable; it is not.
const DEATH_AGES = [70, 75, 78, 80, 82, 85, 88, 90];

/** Sentinel for "let the optimizer choose" — Radix Select forbids "" values. */
const OPTIMIZER_CHOOSES = "__optimizer__";

interface ScenarioFormProps {
  label: string;
  /** Unique per form, used to link labels to controls ("a" / "b"). */
  idPrefix: string;
  value: CompareConstraints;
  onChange: (v: CompareConstraints) => void;
  overrides: CompareOverrides;
  onOverridesChange: (v: CompareOverrides) => void;
  /** Whether the household has Social Security configured for each person. */
  hasSsSelf: boolean;
  hasSsSpouse: boolean;
  /** Policy ids the optimizer can actually run for these inputs. Empty while
   *  loading, or if the lookup failed — then the full menu is shown rather
   *  than blocking the user on a best-effort call. */
  availablePolicies: string[];
  /** One line under the title saying what this side is for. */
  description?: string;
  /** The plan's starting traditional balance: names level-dollar rules by amount. */
  startTraditional?: number | null;
  /** The saved plan's values: fields that differ are highlighted. */
  saved?: Scenario | null;
}

const ADVANCED: FieldKey[] = [
  "policy_id", "irmaa_policy", "conversion_window", "marginal_rate_limit", "max_conversion_per_year",
];

function ScenarioForm({
  label,
  idPrefix,
  value,
  onChange,
  overrides,
  onOverridesChange,
  hasSsSelf,
  hasSsSpouse,
  availablePolicies,
  description,
  saved,
  startTraditional,
}: ScenarioFormProps) {
  const changed = new Set(saved ? changes(saved, { constraints: value, overrides }).map((c) => c.key) : []);
  const advancedChanged = ADVANCED.filter((k) => changed.has(k)).length;
  // A changed field is marked by a tint AND a word, not colour alone.
  const field = (key: FieldKey) => ({
    className: changed.has(key) ? "space-y-1 rounded-md bg-accent/15 ring-1 ring-accent/60 -mx-2 px-2 py-1.5" : "space-y-1",
    "data-changed": changed.has(key) ? "true" : undefined,
  });
  const tag = (key: FieldKey) =>
    changed.has(key) ? (
      <span className="ml-2 text-xs font-medium text-accent-foreground">changed</span>
    ) : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{label}</CardTitle>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </CardHeader>
      <CardContent className="space-y-4">
        <div {...field("required_spending")}>
          <Label htmlFor={`${idPrefix}-spending`}>Annual spending{tag("required_spending")}</Label>
          <CurrencyInput
            id={`${idPrefix}-spending`}
            value={overrides.required_spending}
            onChange={(n) =>
              onOverridesChange({
                ...overrides,
                required_spending: n == null || n <= 0 ? undefined : n,
              })
            }
          />
        </div>

        {hasSsSelf && (
          <div {...field("ss_claim_age_self")}>
            <Label htmlFor={`${idPrefix}-claim-self`}>Your Claim Age{tag("ss_claim_age_self")}</Label>
            <Select
              value={String(overrides.ss_claim_age_self ?? 67)}
              onValueChange={(v) =>
                onOverridesChange({ ...overrides, ss_claim_age_self: Number(v) })
              }
            >
              <SelectTrigger id={`${idPrefix}-claim-self`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CLAIM_AGES.map((a) => (
                  <SelectItem key={a} value={String(a)}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {hasSsSpouse && (
          <div {...field("ss_claim_age_spouse")}>
            <Label htmlFor={`${idPrefix}-claim-spouse`}>Spouse Claim Age{tag("ss_claim_age_spouse")}</Label>
            <Select
              value={String(overrides.ss_claim_age_spouse ?? 67)}
              onValueChange={(v) =>
                onOverridesChange({
                  ...overrides,
                  ss_claim_age_spouse: Number(v),
                })
              }
            >
              <SelectTrigger id={`${idPrefix}-claim-spouse`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CLAIM_AGES.map((a) => (
                  <SelectItem key={a} value={String(a)}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Dynamic spending. Prefilled from the plan so the page SHOWS which
            rule is in force — inheriting it invisibly meant a guardrails plan
            and a fixed-spending plan compared identically on screen. */}
        <div {...field("spending_rule")}>
          <Label htmlFor={`${idPrefix}-spending-rule`}>If markets go badly{tag("spending_rule")}</Label>
          <Select
            value={overrides.spending_rule ?? "fixed"}
            onValueChange={(v) =>
              onOverridesChange({ ...overrides, spending_rule: v as SpendingRule })
            }
          >
            <SelectTrigger id={`${idPrefix}-spending-rule`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fixed">Keep spending the same</SelectItem>
              <SelectItem value="guardrails">Cut back, then recover</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {overrides.spending_rule === "guardrails" && (
          <div {...field("spending_floor")}>
            <Label htmlFor={`${idPrefix}-spending-floor`}>
              Essential spending floor
            {tag("spending_floor")}</Label>
            <CurrencyInput
              id={`${idPrefix}-spending-floor`}
              value={overrides.spending_floor ?? undefined}
              onChange={(n) =>
                onOverridesChange({
                  ...overrides,
                  // Emptied = an explicit null, which CLEARS the stored
                  // floor; undefined would be dropped and inherit it.
                  spending_floor: n == null ? null : n,
                })
              }
            />
          </div>
        )}

        {/* Widow's penalty what-if. The survivor files SINGLE — roughly half
            the bracket widths and half the standard deduction — while keeping
            the larger benefit and all of the RMDs. It is usually the
            highest-tax stretch of a couple's retirement, and the plan of
            record cannot see it. */}
        {hasSsSpouse && (
          <div {...field("first_death")}>
            <Label htmlFor={`${idPrefix}-death`}>Model first death at age{tag("first_death")}</Label>
            <Select
              value={
                overrides.first_death_age != null
                  ? String(overrides.first_death_age)
                  : NO_DEATH
              }
              onValueChange={(v) =>
                onOverridesChange({
                  ...overrides,
                  first_death_age: v === NO_DEATH ? undefined : Number(v),
                  first_death_is_spouse: overrides.first_death_is_spouse ?? true,
                })
              }
            >
              <SelectTrigger id={`${idPrefix}-death`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_DEATH}>Both alive throughout</SelectItem>
                {DEATH_AGES.map((a) => (
                  <SelectItem key={a} value={String(a)}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {overrides.first_death_age != null && (
              <Select
                value={overrides.first_death_is_spouse === false ? "self" : "spouse"}
                onValueChange={(v) =>
                  onOverridesChange({
                    ...overrides,
                    first_death_is_spouse: v === "spouse",
                  })
                }
              >
                <SelectTrigger
                  id={`${idPrefix}-death-who`}
                  aria-label="Who dies first"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="spouse">Spouse dies first</SelectItem>
                  <SelectItem value="self">You die first</SelectItem>
                </SelectContent>
              </Select>
            )}
            <p className="text-xs text-muted-foreground">
              The survivor files single, keeps the larger benefit, and loses the
              smaller.
            </p>
          </div>
        )}

        {/* Less common knobs, collapsed; the summary says how many differ
            from the saved plan so a change is never hidden. */}
        <details className="rounded-md border border-border px-3 py-2" data-testid={`${idPrefix}-advanced`}>
          <summary className="cursor-pointer text-sm font-medium">
            Advanced options
            {advancedChanged > 0 && (
              <span className="ml-2 text-xs font-medium text-accent-foreground">
                ({advancedChanged} changed)
              </span>
            )}
          </summary>
          <div className="mt-3 space-y-4">
        <div {...field("policy_id")}>
          <Label htmlFor={`${idPrefix}-strategy`}>Strategy{tag("policy_id")}</Label>
          <Select
            value={overrides.policy_id ?? OPTIMIZER_CHOOSES}
            onValueChange={(v) =>
              onOverridesChange({
                ...overrides,
                policy_id: v === OPTIMIZER_CHOOSES ? undefined : v,
              })
            }
          >
            <SelectTrigger id={`${idPrefix}-strategy`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={OPTIMIZER_CHOOSES}>
                Optimizer chooses (default)
              </SelectItem>
              {strategyOptions(availablePolicies, startTraditional).map(([id, name]) => (
                <SelectItem key={id} value={id}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {overrides.policy_id &&
            availablePolicies.length > 0 &&
            !availablePolicies.includes(overrides.policy_id) && (
              <p className="text-xs text-destructive" role="alert">
                Not available with this scenario&apos;s inputs — choose another
                strategy or let the optimizer choose.
              </p>
            )}
        </div>

        <div {...field("irmaa_policy")}>
          <Label htmlFor={`${idPrefix}-irmaa`}>Medicare surcharge thresholds{tag("irmaa_policy")}</Label>
          <Select
            value={irmaaChoice(value.irmaa_policy)}
            onValueChange={(v) =>
              onChange({ ...value, irmaa_policy: v as IrmaaPolicy })
            }
          >
            <SelectTrigger id={`${idPrefix}-irmaa`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {IRMAA_CHOICES.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div {...field("conversion_window")}>
          <Label htmlFor={`${idPrefix}-window`}>Conversion Window{tag("conversion_window")}</Label>
          <Select
            value={value.conversion_window ?? "anytime"}
            onValueChange={(v) =>
              onChange({ ...value, conversion_window: v as ConversionWindow })
            }
          >
            <SelectTrigger id={`${idPrefix}-window`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WINDOW_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div {...field("marginal_rate_limit")}>
          <Label htmlFor={`${idPrefix}-maxbracket`}>Max ordinary-income bracket{tag("marginal_rate_limit")}</Label>
          <Select
            value={bracketCapSelectValue(value.marginal_rate_limit)}
            onValueChange={(v) =>
              onChange({
                ...value,
                marginal_rate_limit: v === "none" ? undefined : Number(v),
              })
            }
          >
            <SelectTrigger id={`${idPrefix}-maxbracket`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">No limit</SelectItem>
              {BRACKET_CAP_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div {...field("max_conversion_per_year")}>
          <Label htmlFor={`${idPrefix}-maxconv`}>Max Roth conversion / year{tag("max_conversion_per_year")}</Label>
          <CurrencyInput
            id={`${idPrefix}-maxconv`}
            value={value.max_conversion_per_year}
            onChange={(n) =>
              onChange({
                ...value,
                max_conversion_per_year: n == null || n <= 0 ? undefined : n,
              })
            }
          />
        </div>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// WinnerStrip — each scenario's winning (or forced) strategy
// ---------------------------------------------------------------------------

function WinnerStrip({ result }: { result: CompareResult }) {
  const sides: [string, OptimizationResult][] = [
    ["Baseline", result.result_a],
    ["Your changes", result.result_b],
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {sides.map(([label, res]) => (
        <div
          key={label}
          className="rounded-xl border border-border bg-card px-5 py-3 shadow-folio"
        >
          <p className="text-xs text-muted-foreground">{label}: strategy</p>
          <p className="font-display font-semibold text-primary">
            {policyLabel(res.winning_policy.policy_id, res.starting_traditional_balance)}
            {res.forced_policy ? (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                (forced)
              </span>
            ) : null}
          </p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// YearByYearTable — the two plans side by side, row per year
// ---------------------------------------------------------------------------
//
// The delta cards answer "which is better overall" and the chart answers "how
// do the balances drift". Neither answers "what does each plan actually DO in
// 2029", which is the question you have when reconciling against your own
// spreadsheet — and it is where two strategies with near-identical totals turn
// out to be opposites.

function YearByYearTable({ result }: { result: CompareResult }) {
  const [showAll, setShowAll] = React.useState(false);

  const byYear = new Map<
    number,
    { convA: number; convB: number; taxA: number; taxB: number; balA: number; balB: number }
  >();
  const put = (
    rows: OptimizationResult["yearly_plan"],
    side: "A" | "B",
  ) => {
    for (const r of rows) {
      const e =
        byYear.get(r.year) ??
        { convA: 0, convB: 0, taxA: 0, taxB: 0, balA: 0, balB: 0 };
      // `?? 0` throughout: runs stored before a field existed omit it, and one
      // undefined turns the column total into NaN rather than failing loudly.
      const bal =
        (r.balance_taxable ?? 0) +
        (r.balance_traditional ?? 0) +
        (r.balance_roth ?? 0);
      if (side === "A") {
        e.convA = r.conversion ?? 0; e.taxA = r.total_tax ?? 0; e.balA = bal;
      } else {
        e.convB = r.conversion ?? 0; e.taxB = r.total_tax ?? 0; e.balB = bal;
      }
      byYear.set(r.year, e);
    }
  };
  put(result.result_a.yearly_plan, "A");
  put(result.result_b.yearly_plan, "B");

  const all = Array.from(byYear.entries()).sort((a, b) => a[0] - b[0]);
  // Default to the years where the plans actually differ — on a 30-year plan
  // the conversion decisions cluster in the first decade and the rest is
  // scrolling. "Show all years" is one click away.
  const interesting = all.filter(
    ([, v]) => v.convA > 0 || v.convB > 0,
  );
  const rows = showAll || interesting.length === 0 ? all : interesting;

  const totalA = all.reduce((s, [, v]) => s + v.convA, 0);
  const totalB = all.reduce((s, [, v]) => s + v.convB, 0);

  return (
    <Card data-testid="year-by-year">
      <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Year by Year</CardTitle>
        <Button variant="outline" size="sm" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Conversion years only" : "Show all years"}
        </Button>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="py-2 text-left font-medium">Year</th>
                <th className="py-2 text-right font-medium">Conversion (baseline)</th>
                <th className="py-2 text-right font-medium">Conversion (changes)</th>
                <th className="py-2 text-right font-medium">Tax (baseline)</th>
                <th className="py-2 text-right font-medium">Tax (changes)</th>
                <th className="py-2 text-right font-medium">Balance (baseline)</th>
                <th className="py-2 text-right font-medium">Balance (changes)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([year, v]) => (
                <tr key={year} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 font-medium">{year}</td>
                  <td className="py-1.5 text-right">
                    {v.convA > 0 ? formatCurrency(v.convA) : "—"}
                  </td>
                  <td className="py-1.5 text-right">
                    {v.convB > 0 ? formatCurrency(v.convB) : "—"}
                  </td>
                  <td className="py-1.5 text-right">{formatCurrency(v.taxA)}</td>
                  <td className="py-1.5 text-right">{formatCurrency(v.taxB)}</td>
                  <td className="py-1.5 text-right">{formatCurrency(v.balA)}</td>
                  <td className="py-1.5 text-right">{formatCurrency(v.balB)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-border font-medium">
                <td className="py-2">Total conversions</td>
                <td className="py-2 text-right">{formatCurrency(totalA)}</td>
                <td className="py-2 text-right">{formatCurrency(totalB)}</td>
                <td colSpan={4} />
              </tr>
            </tfoot>
          </table>
        </div>
        {!showAll && interesting.length > 0 && interesting.length < all.length && (
          <p className="text-xs text-muted-foreground mt-2">
            Showing the {interesting.length} year
            {interesting.length === 1 ? "" : "s"} in which either plan converts.
            Two plans can reach almost the same total on opposite schedules, so
            compare the rows, not just the total.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// TotalBalanceChart — overlaid two-line chart
// ---------------------------------------------------------------------------

interface TotalBalanceChartProps {
  result: CompareResult;
}

function TotalBalanceChart({ result }: TotalBalanceChartProps) {
  const data = result.result_a.yearly_plan.map((rowA, i) => {
    const rowB = result.result_b.yearly_plan[i];
    const totalA =
      rowA.balance_taxable + rowA.balance_traditional + rowA.balance_roth;
    const totalB = rowB
      ? rowB.balance_taxable + rowB.balance_traditional + rowB.balance_roth
      : 0;
    return { year: rowA.year, Baseline: totalA, "Your changes": totalB };
  });

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-folio">
      <h3 className="mb-4 font-display text-base font-semibold text-primary">
        Total Portfolio Balance
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis dataKey="year" tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={AXIS_LINE} />
          <YAxis
            tickFormatter={(v) => `$${(v / 1_000_000).toFixed(1)}M`}
            tick={AXIS_TICK}
            axisLine={AXIS_LINE}
            tickLine={AXIS_LINE}
          />
          <Tooltip formatter={(value: number) => formatCurrency(value)} {...TOOLTIP_STYLE} />
          <Legend />
          <Line
            type="monotone"
            dataKey="Baseline"
            stroke={SERIES.emerald}
            strokeWidth={2.5}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="Your changes"
            stroke={SERIES.gold}
            strokeWidth={2.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DeltaCards — summary of differences
// ---------------------------------------------------------------------------

const SIDE_NAMES = { a: "Baseline", b: "Your changes" };

interface DeltaCardsProps {
  result: CompareResult;
}

function DeltaCards({ result }: DeltaCardsProps) {
  // Read the mode off the RESULT, not the page's checkbox — toggling the box
  // after a run must not relabel a result computed the other way.
  const deterministic = result.result_a.monte_carlo_runs === 0;
  const diff = result.difference;
  // Each card says which scenario comes out ahead, in words. The signed A−B
  // figure with a sign rule beneath it was misread in practice, and its
  // red/green was relative to A — so "Scenario B pays less" would have shown
  // in red. The sentence carries the direction on its own.

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Lifetime Taxes Delta */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Lifetime Taxes
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg font-semibold leading-snug text-foreground">
            {describeDelta(diff.lifetime_taxes_delta, "taxes", SIDE_NAMES)}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Total over the plan, in nominal dollars
          </p>
        </CardContent>
      </Card>

      {/* Terminal Estate Delta */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Terminal Estate
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg font-semibold leading-snug text-foreground">
            {describeDelta(diff.terminal_estate_delta, "estate", SIDE_NAMES)}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            At the end of the plan
          </p>
        </CardContent>
      </Card>

      {/* Success Probability Delta. Hidden when the simulation is off: with a
          single return path it is 100% or 0%, and a delta of those is noise
          dressed as a measurement. */}
      {!deterministic && (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Success Probability
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg font-semibold leading-snug text-foreground">
            {describeDelta(diff.success_probability_delta, "success", SIDE_NAMES)}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Share of market scenarios fully funded
          </p>
        </CardContent>
      </Card>
      )}

      {/* Breakeven Year */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Tax Breakeven Year
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold">
            {diff.breakeven_year !== null ? diff.breakeven_year : "—"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Year cumulative tax advantage flips
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ComparePage
// ---------------------------------------------------------------------------

/** Keep *setAvailable* in step with the strategies one scenario can run.
 *  Re-asks (debounced) whenever the scenario's inputs change; the chosen
 *  strategy itself is left out, since it does not change what is available. */
function useScenarioPolicies(
  householdId: string,
  constraints: CompareConstraints,
  overrides: CompareOverrides,
  setAvailable: (p: string[]) => void
) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { policy_id, ...inputs } = overrides;
  const key = JSON.stringify([householdId, constraints, inputs]);
  useEffect(() => {
    if (!householdId) {
      setAvailable([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      listScenarioPolicies(householdId, constraints, inputs)
        .then((r) => {
          if (!cancelled) setAvailable(r.policies);
        })
        .catch(() => {
          if (!cancelled) setAvailable([]);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // key captures every input; the objects themselves change identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}

const DEFAULT_CONSTRAINTS: CompareConstraints = {
  irmaa_policy: "soft",
  conversion_window: "anytime",
};

export default function ComparePage() {
  const [households, setHouseholds] = useState<HouseholdSummary[] | null>(null);
  const [selectedHousehold, setSelectedHousehold] = useState<string>("");
  const [constraintsA, setConstraintsA] =
    useState<CompareConstraints>({ ...DEFAULT_CONSTRAINTS });
  // Both sides start identical, at the plan's own values. B used to open with
  // conversion_window: "pre_rmd" — a difference the user never chose, on a knob
  // they may not have noticed, silently baked into every comparison.
  const [constraintsB, setConstraintsB] =
    useState<CompareConstraints>({ ...DEFAULT_CONSTRAINTS });
  const [overridesA, setOverridesA] = useState<CompareOverrides>({});
  const [overridesB, setOverridesB] = useState<CompareOverrides>({});
  const [hasSsSelf, setHasSsSelf] = useState(false);
  const [hasSsSpouse, setHasSsSpouse] = useState(false);
  const [startTraditional, setStartTraditional] = useState<number | null>(null);
  // Per scenario: each side's own constraints and overrides decide which
  // strategies exist, not the stored plan's.
  const [availableA, setAvailableA] = useState<string[]>([]);
  const [availableB, setAvailableB] = useState<string[]>([]);
  // The household the forms were last prefilled from. Compare stays disabled
  // until it matches the selection: before that the forms hold the page
  // defaults or the PREVIOUS plan's values, and the endpoint takes
  // constraints from the request -- it would run the wrong inputs silently.
  const [prefilledFor, setPrefilledFor] = useState<string | null>(null);
  const [prefillError, setPrefillError] = useState<string | null>(null);
  const [prefillAttempt, setPrefillAttempt] = useState(0);
  // The plan's saved values, which changed fields are highlighted against.
  const [saved, setSaved] = useState<Scenario | null>(null);
  // Each compare request's id; a response for an older request is dropped.
  const requestSeq = useRef(0);
  // Skip the market simulation entirely: every year grows at exactly the
  // plan's Expected Return. This is the interpretable baseline — "what do
  // these strategies do if markets behave as assumed?" — which the page could
  // not show before, since monte_carlo_runs was pinned at 300.
  const [deterministic, setDeterministic] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompareResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    listHouseholds()
      .then((data) => {
        if (!cancelled) {
          setHouseholds(data);
          if (data.length > 0) setSelectedHousehold(data[0].household_id);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Prefill both scenario forms from the household's stored settings so each
  // side starts at reality and the user tweaks from there. Best-effort: if
  // the fetch fails, the knobs stay blank and the stored values still apply.
  useEffect(() => {
    if (!selectedHousehold) return;
    let cancelled = false;
    // A new household invalidates everything shown for the old one.
    setPrefilledFor(null);
    setPrefillError(null);
    setResult(null);
    setError(null);
    requestSeq.current += 1;
    getHousehold(selectedHousehold)
      .then(async (detail) => {
        if (cancelled) return;
        const s = detail.settings;
        const ssSelf = s.ss_pia_self != null;
        const ssSpouse = s.ss_pia_spouse != null;
        // Saved with a searched age and no comparison age: start from the
        // ages the plan's latest run recommended.
        const needAges = (ssSelf && s.ss_claim_age_self == null) ||
          (ssSpouse && s.ss_claim_age_spouse == null);
        const ran = needAges ? await recommendedClaimAges(selectedHousehold).catch(() => null) : null;
        if (cancelled) return;
        setHasSsSelf(ssSelf);
        setHasSsSpouse(ssSpouse);
        setStartTraditional(
          detail.accounts
            .filter((a) => a.account_type === "traditional")
            .reduce((sum, a) => sum + (a.balance ?? 0), 0),
        );
        const base: CompareOverrides = {
          required_spending: s.required_spending,
          spending_rule: s.spending_rule ?? "fixed",
        };
        if (s.spending_floor != null) base.spending_floor = Number(s.spending_floor);
        if (ssSelf) base.ss_claim_age_self = s.ss_claim_age_self ?? ran?.self ?? 67;
        if (ssSpouse) base.ss_claim_age_spouse = s.ss_claim_age_spouse ?? ran?.spouse ?? 67;
        setOverridesA({ ...base });
        setOverridesB({ ...base });

        // Constraints must be prefilled too, and for a harder reason than
        // display. The compare endpoint builds Constraints ENTIRELY from this
        // payload (constraints_from_model) — it never reads the stored ones —
        // so leaving these at defaults did not merely fail to show the plan's
        // values, it REPLACED them. A plan with a 12% conversion-bracket cap
        // was silently compared with no cap at all, on both sides.
        const c = detail.constraints ?? {};
        const storedConstraints: CompareConstraints = {
          irmaa_policy: c.irmaa_policy ?? "soft",
          conversion_window: c.conversion_window ?? "anytime",
          marginal_rate_limit: c.marginal_rate_limit ?? undefined,
          max_conversion_per_year: c.max_conversion_per_year ?? undefined,
          target_estate: c.target_estate ?? undefined,
          preserve_taxable: c.preserve_taxable ?? false,
        };
        setConstraintsA({ ...storedConstraints });
        setConstraintsB({ ...storedConstraints });
        setSaved({ constraints: { ...storedConstraints }, overrides: { ...base } });
        setPrefilledFor(selectedHousehold);
      })
      .catch(() => {
        // Not best-effort: the endpoint REPLACES constraints with whatever
        // the forms send, so comparing on unloaded forms would quietly run
        // the page defaults (or the previous plan's values) as this plan.
        if (!cancelled)
          setPrefillError("Couldn't load this plan's settings, so Compare is off.");
      });

    return () => {
      cancelled = true;
    };
  }, [selectedHousehold, prefillAttempt]);

  // Which strategies each scenario can actually run, for ITS inputs. Purely to
  // avoid offering a choice that 400s — a failure falls back to the full menu
  // rather than blocking the page. Debounced: it runs a search.
  const ready = prefilledFor !== null && prefilledFor === selectedHousehold;
  useScenarioPolicies(ready ? selectedHousehold : "", constraintsA, overridesA, setAvailableA);
  useScenarioPolicies(ready ? selectedHousehold : "", constraintsB, overridesB, setAvailableB);

  async function handleCompare() {
    if (!selectedHousehold || !ready) return;
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await compareScenarios(
        selectedHousehold,
        constraintsA,
        constraintsB,
        overridesA,
        overridesB,
        deterministic ? 0 : undefined
      );
      // A newer request, or a household change, superseded this one.
      if (seq === requestSeq.current) setResult(data);
    } catch (err) {
      if (seq === requestSeq.current)
        setError(err instanceof Error ? err.message : "Comparison failed");
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-3">
          <span className="mt-1 inline-block w-1 h-11 rounded-full bg-accent flex-shrink-0" aria-hidden="true" />
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-primary">
              What-if Analysis
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Run two what-if scenarios of the same plan side by side
            </p>
          </div>
        </div>
        <Button variant="outline" asChild>
          <Link href="/">Back to Dashboard</Link>
        </Button>
      </div>

      {/* Household Selector */}
      <div className="space-y-2">
        <Label>Plan</Label>
        {households === null ? (
          <Skeleton className="h-10 w-64" />
        ) : (
          <Select value={selectedHousehold} onValueChange={setSelectedHousehold}>
            <SelectTrigger className="w-80">
              <SelectValue placeholder="Select a plan" />
            </SelectTrigger>
            <SelectContent>
              {households.map((h) => (
                <SelectItem key={h.household_id} value={h.household_id}>
                  {h.nickname
                    ? h.nickname
                    : `${h.state} — ${h.filing_status === "joint" ? "married filing jointly" : "single"} (${new Date(
                        h.created_at
                      ).toLocaleDateString()})`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Side-by-side constraint forms */}
      <div className="grid gap-4 sm:grid-cols-2">
        <ScenarioForm
          label="Baseline"
          description="Your saved plan. Change it here only to test a different starting point."
          saved={saved}
          idPrefix="a"
          value={constraintsA}
          onChange={setConstraintsA}
          overrides={overridesA}
          onOverridesChange={setOverridesA}
          hasSsSelf={hasSsSelf}
          hasSsSpouse={hasSsSpouse}
          availablePolicies={availableA}
          startTraditional={startTraditional}
        />
        <ScenarioForm
          label="Your changes"
          description="Change any setting to see how the plan responds."
          saved={saved}
          idPrefix="b"
          value={constraintsB}
          onChange={setConstraintsB}
          overrides={overridesB}
          onOverridesChange={setOverridesB}
          hasSsSelf={hasSsSelf}
          hasSsSpouse={hasSsSpouse}
          availablePolicies={availableB}
          startTraditional={startTraditional}
        />
      </div>

      {/* What the comparison will test, in one line. */}
      <p className="text-sm" data-testid="changes-summary">
        {ready && (() => {
          const diff = changes(
            { constraints: constraintsA, overrides: overridesA },
            { constraints: constraintsB, overrides: overridesB },
            startTraditional,
          );
          return diff.length === 0 ? (
            <span className="text-muted-foreground">
              Both sides match. Change a setting under Your changes to ask a what-if question.
            </span>
          ) : (
            <>
              <span className="font-medium">Comparing: </span>
              {changeSummary(diff)}
            </>
          );
        })()}
      </p>

      {/* Compare button */}
      <div className="flex gap-4 items-center flex-wrap">
        <Button
          onClick={handleCompare}
          disabled={loading || !selectedHousehold || !ready}
        >
          {loading ? "Comparing…" : "Compare"}
        </Button>
        {prefillError && (
          <span className="text-sm text-destructive" role="alert">
            {prefillError}{" "}
            <button
              type="button"
              className="underline"
              onClick={() => setPrefillAttempt((n) => n + 1)}
            >
              Retry
            </button>
          </span>
        )}
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="deterministic-toggle"
            checked={deterministic}
            onChange={(e) => setDeterministic(e.target.checked)}
            className="h-4 w-4 accent-primary"
          />
          <span>
            Skip market simulation
            <span className="text-muted-foreground">
              {" "}— every year returns exactly your Expected Return
            </span>
          </span>
        </label>
      </div>
      {deterministic && (
        <p className="text-xs text-muted-foreground" data-testid="deterministic-note">
          Taxes, estate and conversions are computed this way already, so those
          figures will not change. What changes is the <em>ranking</em>: with the
          simulation off, strategies are judged on the steady-return projection
          instead of the average across 300 market scenarios, so the recommendation may
          differ. The share of scenarios with spending funded becomes 100% or 0% and
          carries no information.
        </p>
      )}

      {/* Error */}
      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          <WinnerStrip result={result} />
          <DeltaCards result={result} />
          <TotalBalanceChart result={result} />
          <YearByYearTable result={result} />
        </div>
      )}
    </div>
  );
}
