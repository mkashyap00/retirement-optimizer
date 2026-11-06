"use client";

import React, { useState } from "react";
import type {
  ClaimExclusion,
  JointCandidate,
  JointDeterministicSearch,
  JointScenarioRow,
  JointSearch,
  OptimizationResult,
} from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { STEADY_LABEL } from "@/lib/marketModel";
import { policyLabel } from "@/lib/policyLabels";
import { VERDICT_LABEL } from "@/lib/verdicts";
import { VARIANT_LABELS, candidateKeyLabel, claimAgesLabel } from "@/lib/resultSummary";


function signed(v: number): string {
  if (Math.abs(v) < 0.5) return "±$0";
  return `${v > 0 ? "+" : "−"}${formatCurrency(Math.abs(v))}`;
}

/** The ages each person's axis shows: every age in the grid plus every
 *  excluded age (greyed, with its reason). */
function axis(
  rows: { claim_age_self: number | null; claim_age_spouse: number | null }[],
  exclusions: ClaimExclusion[],
  person: "self" | "spouse"
): (number | null)[] {
  const field = person === "self" ? "claim_age_self" : "claim_age_spouse";
  const ages = new Set<number | null>(rows.map((r) => r[field]));
  exclusions.filter((e) => e.person === person).forEach((e) => ages.add(e.age));
  return Array.from(ages).sort((a, b) => (a ?? 0) - (b ?? 0));
}

function key(self: number | null, spouse: number | null): string {
  return `${self ?? "-"}-${spouse ?? "-"}`;
}

interface Cell {
  key: string;
  claim_age_self: number | null;
  claim_age_spouse: number | null;
  eligible: boolean;
  entered: boolean;
  policy_id: string;
  value: number;
}

/** A selected position in the grid: a scored pair, or an age with no
 *  scenario (excluded), which still says why. */
interface Selection {
  self: number | null;
  spouse: number | null;
}

/** The claim-age grid. Clicking a cell only selects it -- the detail below
 *  shows what the search already measured for that pair. Nothing is run. */
function Matrix({
  cells,
  exclusions,
  winnerKey,
  baseline,
  caption,
  selected,
  onSelect,
  start,
}: {
  /** Starting traditional balance: names level-dollar rules by amount. */
  start?: number | null;
  cells: Cell[];
  exclusions: ClaimExclusion[];
  winnerKey: string;
  /** null: no comparable reference (older runs) -- cells show no difference. */
  baseline: number | null;
  caption: string;
  selected: Selection;
  onSelect: (s: Selection) => void;
}) {
  const byKey = new Map(cells.map((c) => [c.key, c]));
  const rows = axis(cells, exclusions, "self");
  const cols = axis(cells, exclusions, "spouse");
  const single = cols.length === 1 && cols[0] == null;
  const selectedKey = key(selected.self, selected.spouse);
  // A strategy most cells share is named once, in the legend, not in every cell.
  const scoredCells = cells.filter((c) => c.eligible);
  const counts = new Map<string, number>();
  scoredCells.forEach((c) => counts.set(c.policy_id, (counts.get(c.policy_id) ?? 0) + 1));
  const [common, commonN] = Array.from(counts).sort((a, b) => b[1] - a[1])[0] ?? ["", 0];
  const unnamed = scoredCells.length > 1 && commonN * 2 > scoredCells.length ? common : null;

  return (
    <div className="overflow-x-auto">
      <p className="text-xs text-muted-foreground mb-2">{caption}</p>
      <table className="text-xs border-collapse" data-testid="claim-age-matrix">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left font-medium text-muted-foreground">
              {single ? "Your claim age" : "You ↓ / Spouse →"}
            </th>
            {cols.map((c) => (
              <th key={String(c)} className="px-2 py-1 font-medium tabular-nums">
                {single ? "Screening result" : (c ?? "—")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r)}>
              <th className="px-2 py-1 text-left font-medium tabular-nums">{r ?? "—"}</th>
              {cols.map((c) => {
                const k = key(r, c);
                const cell = byKey.get(k);
                const isSelected = k === selectedKey;
                const scored = cell && cell.eligible;
                const isWinner = cell?.key === winnerKey;
                return (
                  <td
                    key={k}
                    data-testid={`cell-${k}`}
                    className={`p-0 border border-border ${
                      !scored ? "bg-muted text-muted-foreground/60" : isWinner ? "bg-accent/30" : ""
                    } ${cell?.entered ? "outline outline-2 outline-secondary" : ""}`}
                  >
                    <button
                      type="button"
                      aria-pressed={isSelected}
                      aria-label={`Inspect ${claimAgesLabel(r, c)}`}
                      onClick={() => onSelect({ self: r, spouse: c })}
                      className={`w-full px-2 py-1 text-center hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${
                        isSelected ? "ring-2 ring-inset ring-primary" : ""
                      }`}
                    >
                      {scored ? (
                        <>
                          <div className="font-semibold tabular-nums">
                            {baseline == null ? "—" : signed(cell.value - baseline)}
                            {isWinner && <span className="ml-1 text-xs font-medium">recommended ages</span>}
                          </div>
                          {cell.policy_id !== unnamed && (
                            <div className="text-xs text-muted-foreground truncate max-w-[8rem]">
                              {policyLabel(cell.policy_id, start)}
                            </div>
                          )}
                        </>
                      ) : cell ? (
                        "entered · not eligible"
                      ) : (
                        "excluded"
                      )}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-muted-foreground mt-2" data-testid="matrix-legend">
        Outlined: your entered ages. Greyed: ages not available (listed below).
        {unnamed && <> Cells without a strategy name: {policyLabel(unnamed, start)}.</>}
      </p>
      <ExclusionList exclusions={exclusions} />
    </div>
  );
}

/** Every unavailable age, visible -- not only on hover. Consecutive ages
 *  with the same reason share a line: "You at 62–64: salary paid …". */
function ExclusionList({ exclusions }: { exclusions: ClaimExclusion[] }) {
  if (exclusions.length === 0) return null;
  const lines: { person: string; from: number; to: number; reason: string }[] = [];
  [...exclusions]
    .sort((a, b) => a.person.localeCompare(b.person) || a.age - b.age)
    .forEach((e) => {
      const last = lines[lines.length - 1];
      if (last && last.person === e.person && last.reason === e.reason && last.to === e.age - 1) last.to = e.age;
      else lines.push({ person: e.person, from: e.age, to: e.age, reason: e.reason });
    });
  return (
    <ul className="mt-1 text-xs text-muted-foreground list-disc pl-5" data-testid="exclusion-list">
      {lines.map((l) => (
        <li key={`${l.person}-${l.from}`}>
          {l.person === "self" ? "You" : "Spouse"} at {l.from === l.to ? l.from : `${l.from}–${l.to}`}: {l.reason}
        </li>
      ))}
    </ul>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="w-48 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="tabular-nums">{children}</dd>
    </div>
  );
}

function exclusionReasons(exclusions: ClaimExclusion[], sel: Selection): string[] {
  return exclusions
    .filter((e) => (e.person === "self" && e.age === sel.self) || (e.person === "spouse" && e.age === sel.spouse))
    .map((e) => `${e.person === "self" ? "You" : "Spouse"} at ${e.age}: ${e.reason}`);
}

function Tags({ entered, recommended }: { entered: boolean; recommended: boolean }) {
  return (
    <>
      {recommended && (
        <span className="ml-2 rounded-full bg-accent/40 px-2 py-0.5 text-xs font-medium">Recommended ages</span>
      )}
      {entered && (
        <span className="ml-2 rounded-full border border-secondary/50 px-2 py-0.5 text-xs font-medium">
          Your entered ages
        </span>
      )}
    </>
  );
}

/** "$2,326 lower modeled score than the recommendation". */
function versus(diff: number): string {
  if (Math.abs(diff) < 0.5) return "Same modeled score as the recommendation";
  return `${formatCurrency(Math.abs(diff))} ${diff > 0 ? "higher" : "lower"} modeled score than the recommendation`;
}

/** What the joint search measured for one pair -- read from the stored
 *  result, never recomputed. The plain answer first; sample counts and the
 *  separate figures under Technical details. */
function JointCellDetail({
  row,
  sel,
  search,
  winner,
  start,
}: {
  start?: number | null;
  row: JointScenarioRow | undefined;
  sel: Selection;
  search: JointSearch;
  winner: JointCandidate;
}) {
  const ages = claimAgesLabel(sel.self, sel.spouse);
  const reasons = exclusionReasons(search.exclusions, sel);
  const recommendedPair = row != null && row.claim_age_self === winner.claim_age_self &&
    row.claim_age_spouse === winner.claim_age_spouse;
  const n1 = search.stages.stage1_runs;
  const final = row?.final ?? null;
  const isWinner = recommendedPair && final?.policy_id === winner.policy_id;
  const cmp = final && row ? search.comparisons[`${final.policy_id}@${row.key}`] : undefined;
  // The winner's own score on the first n1 paths. Older runs lack it, and a
  // full-sample score is no substitute: it is a mean over other paths.
  const winnerS1 = search.stages.winner_stage1_score;

  return (
    <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm space-y-2" data-testid="cell-detail">
      <p className="font-semibold text-primary">
        {ages || "This pair"}
        <Tags entered={!!row?.entered} recommended={recommendedPair} />
      </p>
      {!row || !row.eligible ? (
        <p data-testid="cell-detail-excluded">
          Not available{reasons.length ? `: ${reasons.join("; ")}` : "."}
        </p>
      ) : (
        <>
          <dl className="space-y-1">
            <Fact label="Strategy">{policyLabel((final ?? row.stage1).policy_id, start)}</Fact>
            <Fact label="Compared with the recommendation">
              <span data-testid="cell-detail-comparison">
                {isWinner
                  ? "This is the recommendation."
                  : final
                    ? <>{versus(final.score - winner.score)}{cmp && <> · {VERDICT_LABEL[cmp.verdict]}</>}</>
                    : "Screened during the search; not selected for detailed comparison."}
              </span>
            </Fact>
          </dl>
          <details className="text-xs text-muted-foreground" data-testid="cell-detail-technical">
            <summary className="cursor-pointer">Technical details</summary>
            <dl className="mt-1 space-y-1">
              {/* A difference only: a mean over the first paths is comparable
                  with another mean over them, not with a full-sample score. */}
              <Fact label={`First ${n1} market scenarios`}>
                {policyLabel(row.stage1.policy_id, start)}:{" "}
                {winnerS1 == null
                  ? "Screening comparison unavailable for this saved run."
                  : recommendedPair && row.stage1.policy_id === winner.policy_id
                    ? "the recommendation's own screening result, which the other pairs are compared with"
                    : `${signed(row.stage1.score - winnerS1)} vs the recommendation in the same scenarios`}
              </Fact>
              <Fact label={`All ${search.stages.final_runs} market scenarios`}>
                {final
                  ? `${policyLabel(final.policy_id, start)}: ${formatCurrency(final.score)}`
                  : `Not tested on all ${search.stages.final_runs}.`}
              </Fact>
              <Fact label={STEADY_LABEL}>
                {policyLabel(row.deterministic.policy_id, start)}: {formatCurrency(row.deterministic.value)}{" "}
                ({row.deterministic.policies} strategies compared)
              </Fact>
            </dl>
          </details>
        </>
      )}
    </div>
  );
}

function JointBody({ result, search }: { result: OptimizationResult; search: JointSearch }) {
  const winner = result.joint_winner!;
  const n1 = search.stages.stage1_runs;
  const [sel, setSel] = useState<Selection>({ self: winner.claim_age_self, spouse: winner.claim_age_spouse });
  const cells: Cell[] = search.scenarios.map((s) => ({
    ...s,
    policy_id: s.stage1.policy_id,
    value: s.stage1.score,
  }));
  const winnerScenario = key(winner.claim_age_self, winner.claim_age_spouse);
  const row = search.scenarios.find((s) => s.key === key(sel.self, sel.spouse));
  // Runs saved before every finalist was listed with the alternatives keep
  // the missing ones here, so none is lost.
  const listed = new Set([winner.key, ...result.alternative_policies.map((a) => a.key)]);
  const unlisted = search.stages.finalists.filter((f) => !listed.has(f.key));
  return (
    <>
      <Matrix
        start={result.starting_traditional_balance}
        cells={cells}
        exclusions={search.exclusions}
        winnerKey={winnerScenario}
        baseline={search.stages.winner_stage1_score ?? null}
        caption={
          `The initial ${n1} market scenarios are included in the final ${search.stages.final_runs}. ` +
          `This grid shows the initial comparison using ${n1} market scenarios. A strategy that ` +
          `looks better here may rank lower when tested using all ${search.stages.final_runs}. ` +
          (search.stages.winner_stage1_score == null
            ? "Screening comparison unavailable for this saved run. "
            : "") +
          "Select a cell to inspect its results; this does not start another calculation."
        }
        selected={sel}
        onSelect={setSel}
      />
      <JointCellDetail row={row} sel={sel} search={search} winner={winner}
        start={result.starting_traditional_balance} />
      {unlisted.length > 0 && (
        <div className="space-y-1" data-testid="joint-finalists">
          <h3 className="text-sm font-semibold text-primary">
            Other strategies tested using all {search.stages.final_runs} market scenarios
          </h3>
          <ul className="text-xs space-y-0.5">
            {unlisted.map((f) => (
              <li key={f.key}>
                {policyLabel(f.policy_id, result.starting_traditional_balance)} · {claimAgesLabel(f.claim_age_self, f.claim_age_spouse)}:{" "}
                {formatCurrency(f.score)} ({signed(f.score - winner.score)})
                {search.comparisons[f.key] && <> · {VERDICT_LABEL[search.comparisons[f.key].verdict]}</>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <details className="text-xs text-muted-foreground" data-testid="search-technical">
        <summary className="cursor-pointer">Technical details</summary>
        <p className="mt-1">{search.assumptions.magi_proxy_note}</p>
      </details>
    </>
  );
}

/** Longevity checks: the top candidates rebuilt under other horizons and
 *  lifespans. One row per candidate, one column per check, each cell against
 *  the recommendation under the same check. Reported, never used to rank. */
export function LongevityChecks({ result }: { result: OptimizationResult }) {
  const search = result.search;
  if (search?.mode !== "joint" || search.sensitivity.length === 0) return null;
  const winnerKey = result.joint_winner?.key ?? search.sensitivity[0].results[0]?.key;
  // Every candidate any check reports, the recommendation first.
  const keys: string[] = [];
  search.sensitivity.forEach((row) => row.results.forEach((r) => {
    if (!keys.includes(r.key)) keys.push(r.key);
  }));
  keys.sort((a, b) => Number(b === winnerKey) - Number(a === winnerKey));
  const cell = (variant: string, k: string) =>
    search.sensitivity.find((row) => row.variant === variant)?.results.find((r) => r.key === k);

  return (
    <div className="space-y-2">
      <table className="w-full text-xs" data-testid="joint-sensitivity">
        <thead>
          <tr className="text-left text-muted-foreground border-b border-border">
            <th className="px-2 py-1 font-medium">Strategy and claim ages</th>
            {search.sensitivity.map((row) => (
              <th key={row.variant} className="px-2 py-1 font-medium text-right">
                {VARIANT_LABELS[row.variant] ?? row.variant}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const { strategy, ages } = candidateKeyLabel(k, result.starting_traditional_balance);
            const isWinner = k === winnerKey;
            return (
              <tr key={k} className="border-b border-border/60" data-testid={`longevity-row-${k}`}>
                <td className="px-2 py-1">
                  <span className="font-medium">{isWinner ? "Recommendation: " : ""}{strategy}</span>
                  {ages && <span className="ml-1 text-muted-foreground">· {ages}</span>}
                </td>
                {search.sensitivity.map((row) => {
                  const r = cell(row.variant, k);
                  if (!r) return <td key={row.variant} className="px-2 py-1 text-right text-muted-foreground">—</td>;
                  return (
                    <td
                      key={row.variant}
                      className={`px-2 py-1 text-right tabular-nums ${
                        !isWinner && r.vs_winner > 0 ? "text-amber-800 font-medium" : ""
                      }`}
                    >
                      {isWinner ? formatCurrency(r.score) : signed(r.vs_winner)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          <tr data-testid="longevity-holds">
            <td className="px-2 py-1 text-muted-foreground">Highest among the strategies checked?</td>
            {search.sensitivity.map((row) => (
              <td key={row.variant} className="px-2 py-1 text-right font-medium">
                {row.results.every((r) => r.vs_winner <= 0) ? "Yes" : "No"}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="text-xs text-muted-foreground">
        Recommendation row: its modeled score under each check. Other rows: the difference from the
        recommendation under the same check (a positive amount scores higher). These checks do not
        change the ranking.
      </p>
    </div>
  );
}

/** "The recommendation stays highest in 1 of 4 checks." */
export function longevitySummary(result: OptimizationResult): string | null {
  const search = result.search;
  if (search?.mode !== "joint" || search.sensitivity.length === 0) return null;
  const n = search.sensitivity.length;
  const holds = search.sensitivity.filter((row) => row.results.every((r) => r.vs_winner <= 0)).length;
  return (
    `The recommendation is highest among the strategies checked in ${holds} of ${n} checks of ` +
    `other plan lengths and lifespans${holds < n ? "; in the others another strategy scores higher" : ""}. ` +
    `These checks do not change the ranking.`
  );
}

/** "We compared 48 combinations of your and your spouse's claim ages ..." */
export function explorationSummary(result: OptimizationResult): string | null {
  const search = result.search;
  if (!search) return null;
  const rows = search.mode === "joint_deterministic" ? search.deterministic_matrix : search.scenarios;
  const eligible = rows.filter((s) => s.eligible).length;
  const couple = rows.some((s) => s.claim_age_spouse != null);
  const what = couple
    ? `${eligible} combinations of your and your spouse's claim ages`
    : `${eligible} of your claim ages`;
  if (search.mode === "joint_deterministic") {
    return `We compared ${what} on the steady-return projection, without market simulation.`;
  }
  return (
    `We compared ${what} using ${search.stages.stage1_runs} market scenarios. We then tested ` +
    `the ${search.stages.finalists.length} leading strategies, along with your baseline options, ` +
    `using ${search.stages.final_runs} market scenarios.`
  );
}

function DeterministicBody({ result, search }: { result: OptimizationResult; search: JointDeterministicSearch }) {
  const eligible = search.deterministic_matrix.filter((c) => c.eligible);
  const best = Math.max(...eligible.map((c) => c.value));
  const w = result.winning_policy;
  const [sel, setSel] = useState<Selection>({
    self: w.claim_age_self ?? null, spouse: w.claim_age_spouse ?? null,
  });
  const cell = search.deterministic_matrix.find((c) => c.key === key(sel.self, sel.spouse));
  const winnerKey = key(w.claim_age_self ?? null, w.claim_age_spouse ?? null);
  const reasons = exclusionReasons(search.exclusions, sel);
  return (
    <>
      <Matrix
        start={result.starting_traditional_balance}
        cells={search.deterministic_matrix}
        exclusions={search.exclusions}
        winnerKey={winnerKey}
        baseline={best}
        caption="No market simulation: each pair's best strategy on the steady-return projection, against the best pair. Select a cell to inspect its results; this does not start another calculation."
        selected={sel}
        onSelect={setSel}
      />
      <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs space-y-2" data-testid="cell-detail">
        <p className="text-sm font-semibold text-primary">
          {claimAgesLabel(sel.self, sel.spouse) || "This pair"}
          <Tags entered={!!cell?.entered} recommended={cell?.key === winnerKey} />
        </p>
        {!cell || !cell.eligible ? (
          <p data-testid="cell-detail-excluded">
            Not available{reasons.length ? `: ${reasons.join("; ")}` : "."}
          </p>
        ) : (
          <dl>
            <Fact label={STEADY_LABEL}>
              {policyLabel(cell.policy_id, result.starting_traditional_balance)}: {formatCurrency(cell.value)}
              {cell.key !== winnerKey && ` (${signed(cell.value - best)} vs the best pair)`}
            </Fact>
          </dl>
        )}
      </div>
    </>
  );
}

/** Claim-age exploration: the pairs and what the search measured for each.
 *  Rendered inside a results section. Inspect-only. */
export function ClaimSearchPanel({ result }: { result: OptimizationResult }) {
  const search = result.search;
  if (!search) return null;
  return (
    <div className="space-y-4" data-testid="claim-search-panel">
      {search.mode === "joint" ? (
        <JointBody result={result} search={search} />
      ) : (
        <DeterministicBody result={result} search={search} />
      )}
    </div>
  );
}
