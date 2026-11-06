"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Trash2 } from "lucide-react";
import { listHouseholds, listRuns, deleteHousehold, getActiveOptimizeJob } from "@/lib/api";
import { latestOptimizedRun } from "@/lib/runs";
import type { HouseholdSummary, OptimizeJob, RunSummary } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// ---------------------------------------------------------------------------
// HouseholdCard
// ---------------------------------------------------------------------------

interface HouseholdCardProps {
  household: HouseholdSummary;
  onDeleted: (id: string) => void;
  /** The background job running for this plan, if any. */
  activeJobId?: string | null;
}

function HouseholdCard({ household, onDeleted, activeJobId }: HouseholdCardProps) {
  const router = useRouter();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  // undefined = still loading; null = no runs yet.
  const [latest, setLatest] = useState<RunSummary | null | undefined>(undefined);
  const [runsFailed, setRunsFailed] = useState(false);
  const [runsAttempt, setRunsAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRunsFailed(false);
    listRuns(household.household_id)
      .then((runs) => !cancelled && setLatest(latestOptimizedRun(runs)))
      // Unknown is not "never run": keep View results, disabled.
      .catch(() => !cancelled && setRunsFailed(true));
    return () => {
      cancelled = true;
    };
  }, [household.household_id, runsAttempt]);

  async function handleDelete() {
    const label = household.nickname ?? `${household.state} — ${household.filing_status}`;
    if (
      !window.confirm(
        `Delete plan "${label}"?\n\nThis will permanently remove the household and all its optimization runs. This cannot be undone.`
      )
    ) {
      return;
    }
    setDeleteLoading(true);
    try {
      await deleteHousehold(household.household_id);
      onDeleted(household.household_id);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Delete failed");
      setDeleteLoading(false);
    }
  }

  return (
    <Card className="relative shadow-folio border-border transition-shadow hover:shadow-lg flex flex-col">
      {/* Gold top accent — the product signature */}
      <span className="absolute inset-x-0 top-0 h-0.5 rounded-t-[inherit] bg-accent" aria-hidden="true" />
      <CardHeader>
        <div className="flex items-center gap-2 flex-wrap">
          <CardTitle className="font-display text-lg text-primary">
            {household.nickname ?? household.state}
          </CardTitle>
          <Badge variant="secondary">
            {household.filing_status === "joint" ? "Married filing jointly" : "Single"}
          </Badge>
        </div>
        <CardDescription data-testid="plan-latest-run">
          {household.state} ·{" "}
          {latest === undefined
            ? runsFailed ? "Latest run unavailable" : "…"
            : latest
              ? `Last run ${formatDateTime(latest.created_at)} · ${
                  latest.claim_search ? "Conversions + claim ages" : "Conversions only"
                }`
              : "No results yet"}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1">
        {latest === null && !activeJobId && (
          <p className="text-sm text-muted-foreground" data-testid="plan-unfinished">
            Saved, but no run has completed.
          </p>
        )}
        {runsFailed && (
          <p className="text-sm text-destructive mb-2" data-testid="plan-runs-failed">
            Could not load this plan&apos;s runs.{" "}
            <button
              type="button"
              className="underline underline-offset-2"
              onClick={() => setRunsAttempt((n) => n + 1)}
            >
              Try again
            </button>
          </p>
        )}
        {errorMsg && <p className="text-sm text-destructive mb-2">{errorMsg}</p>}
      </CardContent>
      {/* View the saved results, or delete the plan. Changing inputs is a
          New Plan (copied from this one) or a What-if; the holdings are
          shared by every plan, so Portfolio lives in the top bar only. */}
      <CardFooter className="gap-2 justify-between">
        {/* One action for the plan's state: a search running, results to
            view, or -- the exception -- a plan saved but never run, which
            reopens Review for that same plan (no copy). */}
        {activeJobId ? (
          <Button variant="outline" onClick={() => router.push(`/jobs/${activeJobId}`)}
            data-testid="view-progress">
            View progress
          </Button>
        ) : latest === null ? (
          <Button onClick={() => router.push(`/wizard?resume=${household.household_id}`)}
            data-testid="finish-setup">
            Finish setup and run
          </Button>
        ) : (
          <Button
            variant="outline"
            disabled={!latest}
            onClick={() => latest && router.push(`/results/${latest.run_id}`)}
            data-testid="view-results"
          >
            View results
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={handleDelete}
          disabled={deleteLoading}
          aria-label="Delete plan"
          title="Delete plan"
          className="text-muted-foreground hover:text-destructive"
          data-testid="delete-plan"
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      </CardFooter>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Dashboard page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const [households, setHouseholds] = useState<HouseholdSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [networkDown, setNetworkDown] = useState(false);
  // A claim-age search survives a page reload: resume polling it.
  const [activeJob, setActiveJob] = useState<OptimizeJob | null>(null);

  useEffect(() => {
    getActiveOptimizeJob()
      .then((j) => setActiveJob(j ?? null))
      .catch(() => {}); // progress is a convenience; the cards work without it
  }, []);

  const loadHouseholds = useCallback(() => {
    setHouseholds(null);
    setError(null);
    setNetworkDown(false);
    listHouseholds()
      .then((data) => setHouseholds(data))
      .catch((err: Error) => {
        if (err instanceof TypeError) {
          setNetworkDown(true);
        } else {
          setError(err.message);
        }
      });
  }, []);

  function handleDeleted(id: string) {
    setHouseholds((prev) => (prev ? prev.filter((h) => h.household_id !== id) : prev));
  }

  useEffect(() => {
    loadHouseholds();
  }, [loadHouseholds]);

  return (
    <div className="space-y-8">
      {/* Page action row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3">
          {/* Gold accent bar — the product signature */}
          <span className="mt-1 inline-block w-1 h-10 rounded-full bg-accent flex-shrink-0" aria-hidden="true" />
          <div>
            <h2 className="font-display text-xl font-semibold tracking-tight text-primary">
              Your Plans
            </h2>
            <p className="text-muted-foreground text-sm mt-0.5">
              Optimize Roth conversions and withdrawal timing
            </p>
          </div>
        </div>
        <Button asChild>
          <Link href="/wizard">New Plan</Link>
        </Button>
      </div>

      {/* Backend-down friendly state */}
      {networkDown && (
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="text-base">
              Can&apos;t reach the optimizer service
            </CardTitle>
            <CardDescription>
              The backend at{" "}
              <code className="text-xs bg-muted px-1 py-0.5 rounded">
                localhost:8000
              </code>{" "}
              isn&apos;t responding. Make sure the backend is running — you can
              start both servers with{" "}
              <code className="text-xs bg-muted px-1 py-0.5 rounded">
                bash scripts/start.sh
              </code>
              .
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Button variant="outline" onClick={loadHouseholds}>
              Retry
            </Button>
          </CardFooter>
        </Card>
      )}

      {/* Generic error */}
      {error && (
        <p className="text-sm text-destructive">
          Failed to load households: {error}
        </p>
      )}

      {/* Loading skeleton */}
      {households === null && !error && !networkDown && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {households !== null && households.length === 0 && (
        <Card className="max-w-sm mx-auto text-center">
          <CardHeader>
            <CardTitle>No plans yet</CardTitle>
            <CardDescription>
              Create your first retirement plan to get started.
            </CardDescription>
          </CardHeader>
          <CardFooter className="justify-center">
            <Button asChild>
              <Link href="/wizard">New Plan</Link>
            </Button>
          </CardFooter>
        </Card>
      )}

      {/* Household cards */}
      {households !== null && households.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {households.map((h) => (
            <HouseholdCard
              key={h.household_id}
              household={h}
              onDeleted={handleDeleted}
              activeJobId={activeJob?.household_id === h.household_id ? activeJob.id : null}
            />
          ))}
        </div>
      )}
    </div>
  );
}
