"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useWizardStore } from "@/stores/wizardStore";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { createHousehold, getActiveOptimizeJob, updateHousehold } from "@/lib/api";
import { savePlanModes } from "@/lib/planModes";
import { startOptimization } from "@/lib/startRun";
import { ClaimAgeSetup } from "@/components/ClaimAgeSetup";
import { useClaimPreview } from "@/lib/useClaimPreview";
import { controlsFor, runProblems, searchSummary } from "@/lib/claimSetup";
import type { HouseholdPayload } from "@/lib/types";
import { validateStep } from "../schemas";
import { IRMAA_LABELS } from "@/lib/labels";
import { projectionEndYear } from "@/lib/planHorizon";
import { householdHorizon, planPayload } from "@/lib/planPayload";
import { capitalGainsLines } from "@/lib/capitalGains";
import { StepHeader, money, claimPreviewBody } from "./shared";

function limitsSummary(data: HouseholdPayload): string {
  return [
    data.constraints.target_estate ? `target estate ${money(data.constraints.target_estate)}` : null,
    data.constraints.max_conversion_per_year
      ? `max ${money(data.constraints.max_conversion_per_year)}/yr`
      : null,
    data.constraints.marginal_rate_limit != null
      ? `up to the ${Math.round(Number(data.constraints.marginal_rate_limit) * 100)}% bracket`
      : null,
  ].filter(Boolean).join(" · ") || "none set";
}

// ---------------------------------------------------------------------------
// Step 6: Review and run -- a summary with Edit links, and the one action
// ---------------------------------------------------------------------------

const WINDOW_DISPLAY: Record<string, string> = {
  anytime: "Anytime",
  pre_medicare: "Before Medicare (65)",
  pre_rmd: "Before RMDs (73, or 75 if born 1960+)",
  pre_ss: "Before Social Security",
};

const STEP_NAMES = ["Household", "Assumptions", "Accounts", "Income and Social Security", "Spending and goals"];

/** One line of the review summary, with a link back to its step. */
function ReviewSection({
  title,
  step,
  children,
}: {
  title: string;
  step: number;
  children: React.ReactNode;
}) {
  const goToStep = useWizardStore((s) => s.goToStep);
  return (
    <div className="flex items-start justify-between gap-3 text-sm">
      <div>
        <p className="font-medium text-foreground">{title}</p>
        <div className="text-muted-foreground">{children}</div>
      </div>
      <Button variant="link" size="sm" className="h-auto p-0" onClick={() => goToStep(step)}>
        Edit<span className="sr-only"> {title.toLowerCase()}</span>
      </Button>
    </div>
  );
}

/** The fixed annual amounts the level-dollar strategies try: 5%, 10% and
 *  20% of the starting traditional balance (backend search._LEVEL_RULES). */
export const LEVEL_SHARES = [0.05, 0.1, 0.2] as const;

export function StepReview() {
  const router = useRouter();
  const data = useWizardStore((s) => s.data);
  const clearDraft = useWizardStore((s) => s.clearDraft);
  const goToStep = useWizardStore((s) => s.goToStep);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  // The saved plan this draft belongs to (persisted with the draft, so it
  // survives leaving the wizard and reloading): saved by this step earlier,
  // or an unfinished plan resumed from the dashboard. Running reuses it --
  // updated in place if the inputs changed -- and never saves a copy.
  const resume = useWizardStore((s) => s.resume);
  const setResume = useWizardStore((s) => s.setResume);
  const unconfirmed = useWizardStore((s) => s.unconfirmedModes);
  const chooseMode = useWizardStore((s) => s.chooseMode);
  const [savedBusy, setSavedBusy] = useState<string | null>(null);
  const claimModes = useWizardStore((s) => s.claimModes);
  const claim = useClaimPreview({ body: claimPreviewBody(data) });
  const summary = searchSummary(claim.preview, claimModes);
  const problems = runProblems(claim.preview, claimModes);
  // A step left invalid (reached through the rail, or edited after Next).
  const invalidStep = STEP_NAMES.findIndex((_, i) => !validateStep(i, data, claimModes).success);

  // One action: save the plan and start the run its setup describes -- a
  // background claim-age search when either age is searched, otherwise the
  // conversion optimizer directly. No preliminary fixed-age run.
  async function handleOptimize() {
    if (invalidStep >= 0 || unconfirmed.length > 0) return;
    setLoading(true);
    setError(null);
    setBusyJobId(null);
    setSavedBusy(null);
    try {
      const payload = planPayload(data);
      const dataKey = JSON.stringify(payload);
      if (summary.searching && !resume) {
        // Usually refuses BEFORE saving. It cannot guarantee it: another
        // search can start between this check and the submit (see below).
        const active = await getActiveOptimizeJob().catch(() => null);
        if (active) {
          setBusyJobId(active.id);
          return;
        }
      }
      let household_id: string;
      if (resume) {
        household_id = resume.householdId;
        if (resume.savedKey !== dataKey) {
          await updateHousehold(household_id, payload);
          setResume({ householdId: household_id, savedKey: dataKey });
        }
      } else {
        household_id = (await createHousehold(payload)).household_id;
        setResume({ householdId: household_id, savedKey: dataKey });
      }
      // Recorded with the plan, so finishing it later starts the same run.
      savePlanModes(household_id, claimModes);
      const started = await startOptimization({
        householdId: household_id,
        nickname: data.household.nickname || null,
        controls: controlsFor(claim.preview, claimModes),
      });
      if (started.kind === "busy") {
        // Saved, but ITS search did not start. Keep the draft and stay here;
        // the other search is not this plan's.
        setSavedBusy(started.jobId);
        return;
      }
      clearDraft();
      if (started.kind === "run") router.push(`/results/${started.runId}`);
      else router.push(`/jobs/${started.jobId}`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "An unexpected error occurred."
      );
    } finally {
      setLoading(false);
    }
  }

  const isJoint = data.household.filing_status === "joint";
  const totalBalance = data.accounts.reduce((sum, a) => sum + (a.balance ?? 0), 0);
  const traditional = data.accounts
    .filter((a) => a.account_type === "traditional")
    .reduce((sum, a) => sum + (a.balance ?? 0), 0);
  const totalIncome = data.income.reduce((sum, i) => sum + (i.amount ?? 0), 0);
  const endYear = projectionEndYear(householdHorizon(data));
  const hh = data.household;

  return (
    <div>
      <StepHeader
        title="Review and run"
        description="Check your choices, then start the calculation."
      />

      <div className="flex flex-col gap-5">
        <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3" data-testid="review-summary">
          <h3 className="text-sm font-semibold font-display text-foreground">Your plan</h3>
          <ReviewSection title="Household" step={0}>
            <span className="block">
              {[
                hh.nickname,
                isJoint ? "Married filing jointly" : "Single",
                hh.state,
                `born ${hh.self_birth_date || "—"}` + (isJoint ? ` and ${hh.spouse_birth_date || "—"}` : ""),
              ].filter(Boolean).join(" · ")}
            </span>
            <span className="block" data-testid="review-horizon">
              {`Planned through age ${hh.self_death_age ?? "—"}` +
                (isJoint ? ` (you) and ${hh.spouse_death_age ?? "—"} (spouse)` : "") +
                (endYear != null ? ` · projection ends in ${endYear}` : "")}
            </span>
          </ReviewSection>
          <ReviewSection title="Assumptions" step={1}>
            {`Inflation ${(data.settings.inflation * 100).toFixed(1)}% · return ` +
              `${(data.settings.nominal_return * 100).toFixed(1)}% · ` +
              `${(IRMAA_LABELS[data.constraints.irmaa_policy] ?? data.constraints.irmaa_policy).toLowerCase()} · ` +
              `conversions ${(WINDOW_DISPLAY[data.constraints.conversion_window] ?? data.constraints.conversion_window).toLowerCase()}` +
              (data.constraints.preserve_taxable ? " · IRA drawn first" : "")}
          </ReviewSection>
          <ReviewSection title="Accounts" step={2}>
            {data.accounts.length
              ? `${data.accounts.length} account${data.accounts.length > 1 ? "s" : ""} · ${money(totalBalance)} in total`
              : "None"}
          </ReviewSection>
          <ReviewSection title="Income and Social Security" step={3}>
            <span className="block">
              {data.income.length
                ? `${data.income.length} income source${data.income.length > 1 ? "s" : ""} · ${money(totalIncome)}/year`
                : "No other income"}
            </span>
            {capitalGainsLines(data.capital_gains).map(([label, value]) => (
              <span key={label} className="block" data-testid="review-gains-line">{`${label}: ${value}`}</span>
            ))}
            {/* Claim ages, receiving status and whether each is searched. */}
            {unconfirmed.length > 0 ? (
              <span className="block" data-testid="review-claim-line">Claim-age choices: confirm below</span>
            ) : (
              summary.people.map((line) => (
                <span key={line} className="block" data-testid="review-claim-line">{line}</span>
              ))
            )}
          </ReviewSection>
          <ReviewSection title="Spending and goals" step={4}>
            <span className="block">
              {`${money(data.settings.required_spending)}/year · ` +
                (data.settings.spending_rule === "guardrails"
                  ? "cut back, then recover" +
                    (data.settings.spending_floor != null
                      ? ` (minimum ${money(data.settings.spending_floor)})`
                      : " (no minimum)")
                  : "kept the same")}
            </span>
            <span className="block">Goals and limits: {limitsSummary(data)}</span>
          </ReviewSection>
        </div>

        {/* What the action will run, right above it. */}
        <div className="rounded-lg border border-border p-4 space-y-3" data-testid="review-run-setup">
          <h3 className="text-sm font-semibold font-display text-foreground">
            {summary.searching ? "Conversions and claim ages" : "Conversion optimization"}
          </h3>
          <p className="text-sm text-muted-foreground" data-testid="review-strategies">
            We&apos;ll compare no conversions, tax-bracket strategies, and fixed annual
            conversion amounts with different stopping years
            {traditional > 0 && (
              <>
                {" "}(up to{" "}
                {LEVEL_SHARES.slice(0, -1).map((f) => money(f * traditional)).join(", ")} or{" "}
                {money(LEVEL_SHARES[LEVEL_SHARES.length - 1] * traditional)}
                {" "}a year: 5%, 10% or 20% of your starting traditional balance)
              </>
            )}
            .
          </p>
          {/* Until the choices are confirmed, a summary would describe a guess. */}
          {unconfirmed.length === 0 && (
            <ClaimAgeSetup
              preview={claim.preview}
              modes={claimModes}
              loading={claim.loading}
              error={claim.error}
            />
          )}
        </div>

        {unconfirmed.length > 0 && (
          <fieldset className="rounded-md border border-amber-300 bg-amber-50 p-4 space-y-3" data-testid="review-confirm-modes">
            <legend className="px-1 text-sm font-semibold text-amber-900">
              Confirm how each claim age is chosen
            </legend>
            <p className="text-sm text-amber-900">
              This plan was saved without a record of these choices, so they are not assumed.
            </p>
            {unconfirmed.map((who) => {
              const age = who === "self" ? data.settings.ss_claim_age_self : data.settings.ss_claim_age_spouse;
              return (
                <div key={who} role="radiogroup" aria-label={`${who === "self" ? "Your" : "Spouse's"} claim age`}
                  className="flex flex-col gap-1 text-sm">
                  <span className="font-medium">{who === "self" ? "You" : "Spouse"}</span>
                  <label className="flex items-center gap-2">
                    <input type="radio" name={`confirm-${who}`} onChange={() => chooseMode(who, "search")}
                      data-testid={`confirm-${who}-search`} />
                    Find the best eligible age{age != null && <> (compared with {age})</>}
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="radio" name={`confirm-${who}`} onChange={() => chooseMode(who, "fixed")}
                      data-testid={`confirm-${who}-fixed`} />
                    Use an age I choose{age != null && <> ({age})</>}
                  </label>
                </div>
              );
            })}
          </fieldset>
        )}

        {invalidStep >= 0 && (
          <Alert variant="destructive" data-testid="review-invalid-step">
            <AlertDescription>
              {STEP_NAMES[invalidStep]} needs attention before running.{" "}
              <button
                type="button"
                className="font-medium underline underline-offset-2"
                onClick={() => goToStep(invalidStep)}
              >
                Fix it
              </button>
            </AlertDescription>
          </Alert>
        )}

        {/* Error alert */}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {savedBusy && (
          <Alert variant="warning" data-testid="review-saved-busy">
            <AlertDescription>
              Your plan was saved, but its search has not started: another search began
              first. Try again here when it finishes, or later with <strong>Finish setup and
              run</strong> on the dashboard — either way this plan is reused, not saved again.{" "}
              <a href={`/jobs/${savedBusy}`} className="font-medium underline underline-offset-2">
                View the other search
              </a>
            </AlertDescription>
          </Alert>
        )}
        {busyJobId && (
          <Alert variant="warning" data-testid="review-busy">
            <AlertDescription>
              Another optimization is already running. Your plan has not been saved yet;
              start it again when that search finishes.{" "}
              <a href={`/jobs/${busyJobId}`} className="font-medium underline underline-offset-2">
                View progress
              </a>
            </AlertDescription>
          </Alert>
        )}

        {/* Submit CTA */}
        <Button
          className="w-full h-12 text-base font-semibold bg-accent text-accent-foreground hover:bg-accent/90 shadow-folio"
          onClick={handleOptimize}
          // Only a preview of the CURRENT inputs, fetched successfully.
          disabled={loading || problems.length > 0 || !claim.ready || invalidStep >= 0 ||
            unconfirmed.length > 0}
          data-testid="review-submit"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              {summary.searching ? "Starting…" : "Optimizing…"}
            </>
          ) : (
            summary.actionLabel
          )}
        </Button>
      </div>
    </div>
  );
}
