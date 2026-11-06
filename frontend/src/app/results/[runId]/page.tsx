"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getRun, BASE_URL, getHealth, generateNarrative, listRuns } from "@/lib/api";
import { latestOptimizedRun } from "@/lib/runs";
import type { HouseholdDetail, OptimizationResult } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SummaryCards } from "@/components/results/SummaryCards";
import { InputsPanel } from "@/components/results/InputsPanel";
import { AlternativesTable } from "@/components/results/AlternativesTable";
import { policyLabel } from "@/lib/policyLabels";
import { BalancesChart } from "@/components/results/BalancesChart";
import { TaxChart } from "@/components/results/TaxChart";
import { ConversionChart } from "@/components/results/ConversionChart";
import { YearTable } from "@/components/results/YearTable";
import {
  ClaimSearchPanel,
  LongevityChecks,
  explorationSummary,
  longevitySummary,
} from "@/components/results/ClaimSearchPanel";
import { ImprovementPanel } from "@/components/results/ImprovementPanel";
import { closeCallSentence, confidenceSentence, rankingRows } from "@/lib/resultSummary";
import { ResultSection } from "@/components/results/ResultSection";
import { MilestoneList } from "@/components/results/ChartFrame";
import { milestones as chartMilestones } from "@/lib/milestones";
import { marketFacts, steadyDefinition } from "@/lib/marketModel";

export default function ResultsPage() {
  // From Next 15 the page's `params` prop is a Promise; a client component
  // reads the route segment with useParams instead.
  const { runId } = useParams<{ runId: string }>();
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [runInputs, setRunInputs] = useState<HouseholdDetail | null>(null);
  const [householdId, setHouseholdId] = useState<string | null>(null);
  const [runCreatedAt, setRunCreatedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [narrativeError, setNarrativeError] = useState<string | null>(null);
  // On a forced run: the plan's latest optimized run, to link back to.
  const [optimizedRunId, setOptimizedRunId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); // re-entered on client-side nav between runs
    getRun(runId)
      .then((run) => {
        if (!cancelled) {
          setResult(run.result);
          setRunInputs(run.inputs ?? null);
          setHouseholdId(run.household_id);
          setRunCreatedAt(run.created_at);
        }
      })
      .catch((err: Error) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [runId]);

  useEffect(() => {
    if (!result?.forced_policy || !householdId) return;
    let cancelled = false;
    listRuns(householdId)
      .then((runs) => {
        const optimized = latestOptimizedRun(runs);
        if (!cancelled && optimized && !optimized.forced_policy && optimized.run_id !== runId) {
          setOptimizedRunId(optimized.run_id);
        }
      })
      .catch(() => {}); // the link is a convenience; the banner stands without it
    return () => { cancelled = true; };
  }, [result, householdId, runId]);

  useEffect(() => {
    getHealth()
      .then((h) => setLlmEnabled(h.llm))
      .catch(() => setLlmEnabled(false));
  }, []);

  function handleGenerateNarrative() {
    setNarrativeLoading(true);
    setNarrativeError(null);
    generateNarrative(runId)
      .then((r) => setNarrative(r.narrative))
      .catch((err: Error) => setNarrativeError(err.message))
      .finally(() => setNarrativeLoading(false));
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-80" />
        <Skeleton className="h-80" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <Alert variant="destructive">
          <AlertTitle>Error loading results</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!result) return null;

  const joint = result.search != null;
  // The run's own market assumptions; older runs take the return from
  // their inputs snapshot.
  const market = marketFacts(result, runInputs?.settings?.nominal_return);
  const firstYear = result.yearly_plan[0]?.year;
  const milestones = chartMilestones(result.yearly_plan, {
    claimAges: joint
      ? { self: result.winning_policy.claim_age_self, spouse: result.winning_policy.claim_age_spouse }
      : result.claim_ages,
    receiving: {
      self: runInputs?.settings?.ss_receiving_self,
      spouse: runInputs?.settings?.ss_receiving_spouse,
    },
    income: runInputs?.income,
  });

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-3">
          {/* Gold accent bar — the product signature */}
          <span className="mt-1 inline-block w-1 h-11 rounded-full bg-accent flex-shrink-0" aria-hidden="true" />
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-primary" data-testid="results-title">
              {runInputs?.household?.nickname || "Optimization results"}
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              {runCreatedAt ? `Run created ${formatDateTime(runCreatedAt)}` : "Your optimized plan"}
            </p>
            {/* Identifiers are for support and cross-checking, not reading. */}
            <details className="mt-1 text-xs text-muted-foreground/80" data-testid="run-details">
              <summary className="cursor-pointer">Run details</summary>
              <p className="mt-1">
                <span className="font-sans">Run ID: </span>
                <span className="font-mono">{runId}</span>
              </p>
              {householdId && (
                <p>
                  <span className="font-sans">Plan (household) ID: </span>
                  <span className="font-mono">{householdId}</span>
                </p>
              )}
              {/* From the inputs snapshot, so it is the name the plan had when
                  this run was made -- the same one the Excel export shows. */}
              {runInputs?.household?.nickname && (
                <p data-testid="plan-nickname">
                  <span className="font-sans">Plan nickname: </span>
                  <span className="font-medium text-foreground/80">{runInputs.household.nickname}</span>
                </p>
              )}
            </details>
          </div>
        </div>
        <div className="flex gap-2">
          {/* Files are auto-saved to reports/ when the run completes; these
              buttons open/download a copy on demand. */}
          <a href={`${BASE_URL}/runs/${runId}/export.csv`} download>
            <Button variant="outline">CSV</Button>
          </a>
          <a href={`${BASE_URL}/runs/${runId}/export.xlsx`} download>
            <Button variant="outline">Excel</Button>
          </a>
          <a
            href={`${BASE_URL}/runs/${runId}/report.pdf`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Button variant="outline">PDF</Button>
          </a>
          {llmEnabled && (
            <Button
              variant="outline"
              onClick={handleGenerateNarrative}
              disabled={narrativeLoading}
              data-testid="generate-ai-summary"
            >
              {narrativeLoading ? "Generating…" : "Generate AI summary"}
            </Button>
          )}
        </div>
      </div>

      {/* AI narrative card */}
      {narrativeError && (
        <Alert variant="destructive">
          <AlertDescription>{narrativeError}</AlertDescription>
        </Alert>
      )}
      {narrative && (
        <div
          className="rounded-xl border border-border bg-card p-6 space-y-2 shadow-folio"
          data-testid="narrative-card"
        >
          <h2 className="font-display text-lg font-semibold text-primary">AI Summary</h2>
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{narrative}</p>
        </div>
      )}

      {/* Forced-policy banner — this plan was requested, not recommended */}
      {result.forced_policy && (
        <Alert variant="warning" data-testid="forced-policy-banner">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Forced-policy run</AlertTitle>
          <AlertDescription>
            This plan shows <strong>{policyLabel(result.forced_policy, result.starting_traditional_balance)}</strong>
            {result.pinned_claim_ages && (
              <>
                {" "}at claim ages{" "}
                <strong data-testid="pinned-claim-ages">
                  {[result.pinned_claim_ages.self, result.pinned_claim_ages.spouse]
                    .filter((a) => a != null)
                    .join(" / ")}
                </strong>
              </>
            )}{" "}
            because you asked to see it.{" "}
            {result.optimizer_pick == null ? (
              <>It is not the optimizer&apos;s recommendation for these inputs.</>
            ) : result.optimizer_pick === result.forced_policy ? (
              <>It is also the optimizer&apos;s own pick for these inputs.</>
            ) : (
              <>
                The optimizer&apos;s own pick for these inputs is{" "}
                <strong>{policyLabel(result.optimizer_pick, result.starting_traditional_balance)}</strong>.
              </>
            )}
            {optimizedRunId && (
              <>
                {" "}
                <a
                  href={`/results/${optimizedRunId}`}
                  className="font-medium underline underline-offset-2"
                  data-testid="back-to-optimized-run"
                >
                  View the optimized run →
                </a>
              </>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* 1. The recommendation, then the qualifications on it. */}
      <SummaryCards
        result={result}
        planName={runInputs?.household?.nickname}
        spendingRule={runInputs?.settings?.spending_rule}
        market={market}
      />

      {result.warnings.length > 0 && (
        <div className="space-y-2">
          {result.warnings.map((w, i) => (
            <Alert key={i} variant="warning">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Advisory</AlertTitle>
              <AlertDescription>{w}</AlertDescription>
            </Alert>
          ))}
        </div>
      )}

      {/* 2. The recommendation against the user's own choices. */}
      <ImprovementPanel result={result} />


      {/* Alternatives -- read-only: another calculation starts from
          changing the inputs and running again, not from a results row. */}
      <AlternativesTable
        alternatives={result.alternative_policies}
        winningPolicyId={result.winning_policy.policy_id}
        winnerSuccessProbability={result.winning_policy.success_probability}
        monteCarloRuns={result.monte_carlo_runs}
        firstYear={firstYear}
        ranking={rankingRows(result)}
        closeCall={closeCallSentence(result) ? confidenceSentence(result) : null}
        steadyReturn={market.meanReturn}
        startTraditional={result.starting_traditional_balance}
        materiality={
          result.materiality ?? (result.search?.mode === "joint" ? result.search.materiality : null)
        }
        optimizerPickId={result.forced_policy ? result.optimizer_pick : undefined}
        winnerFirstConversionYear={
          result.yearly_plan.length > 0
            ? (result.yearly_plan.find((y) => y.conversion > 0)?.year ?? null)
            : undefined
        }
        winnerYear0Conversion={
          result.winning_policy.year0_conversion ?? result.yearly_plan[0]?.conversion
        }
      />

      {/* 4–5. Exploration, collapsed with a one-line summary. */}
      {result.search && (
        <ResultSection
          title="Explore other Social Security claim ages"
          summary={explorationSummary(result)}
          testId="section-claim-ages"
        >
          {/* Inspect-only: a cell shows what the search already measured. */}
          <ClaimSearchPanel result={result} />
        </ResultSection>
      )}
      {longevitySummary(result) && (
        <ResultSection title="What if you live longer or shorter?" summary={longevitySummary(result)} testId="section-longevity">
          <LongevityChecks result={result} />
        </ResultSection>
      )}

      {/* 6. Charts and the year-by-year projection (expected-return case). */}
      <div className="space-y-2 -mb-2">
        <p className="text-sm text-muted-foreground">
          The charts and table below are a {steadyDefinition(market.meanReturn).charAt(0).toLowerCase()}
          {steadyDefinition(market.meanReturn).slice(1)}.
        </p>
        <MilestoneList milestones={milestones} />
      </div>
      {/* Charts grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        <BalancesChart rows={result.yearly_plan} milestones={milestones} />
        <TaxChart rows={result.yearly_plan} milestones={milestones} />
        <div className="lg:col-span-2">
          <ConversionChart rows={result.yearly_plan} milestones={milestones} />
        </div>
      </div>

      {/* Year-by-year table */}
      <div>
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-primary mb-3">
          <span className="inline-block w-1 h-5 rounded-full bg-accent" aria-hidden="true" />
          Year-by-Year Plan
        </h2>
        <p className="text-sm text-muted-foreground mb-3">
          Expand a year (▸) to see why the plan does what it does that year. On the first year that draws on
          your taxable account, <strong>Plan this sale</strong> turns that
          withdrawal into a sell list from your uploaded portfolio.
        </p>
        <YearTable
          rows={result.yearly_plan}
          selfDeathAge={runInputs?.household?.self_death_age}
          spouseDeathAge={runInputs?.household?.spouse_death_age}
          policyId={result.winning_policy.policy_id}
        />
      </div>

      {/* 7. Inputs, assumptions and methodology (runs created before snapshots have none) */}
      {runInputs && (
        <InputsPanel
          inputs={runInputs}
          objective={result.objective}
          taxTables={result.tax_tables}
          claims={{
            joint,
            searched: result.search?.mode === "joint"
              ? {
                  self: result.search.controls.self.mode === "search",
                  spouse: result.search.controls.spouse.mode === "search",
                }
              : result.search?.mode === "joint_deterministic"
                ? (() => {
                    // No stored controls: a person was searched when the
                    // matrix holds more than one of their ages.
                    const m = result.search.deterministic_matrix;
                    return {
                      self: new Set(m.map((c) => c.claim_age_self)).size > 1,
                      spouse: new Set(m.map((c) => c.claim_age_spouse)).size > 1,
                    };
                  })()
                : undefined,
            used: joint
              ? { self: result.winning_policy.claim_age_self, spouse: result.winning_policy.claim_age_spouse }
              : result.claim_ages,
          }}
        />
      )}
    </div>
  );
}
