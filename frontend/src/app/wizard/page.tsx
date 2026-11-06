"use client";

import { useState, useRef, useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { LAST_STEP, useWizardStore } from "@/stores/wizardStore";
import { listHouseholds, getHousehold } from "@/lib/api";
import { loadPlanModes } from "@/lib/planModes";
import type { HouseholdSummary } from "@/lib/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ProgressRail } from "@/components/wizard/ProgressRail";
import { SummaryAside } from "@/components/wizard/SummaryAside";
import { WizardErrorContext } from "@/components/wizard/WizardContext";
import { validateStep } from "@/components/wizard/schemas";
import {
  StepProfile,
  StepAssumptions,
  StepAccounts,
  StepIncomeAndSS,
  StepSpendingGoals,
  StepReview,
} from "@/components/wizard/steps";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Step registry
// ---------------------------------------------------------------------------

const STEP_COMPONENTS = [
  StepProfile,
  StepAssumptions,
  StepAccounts,
  StepIncomeAndSS,
  StepSpendingGoals,
  StepReview,
] as const;

// ---------------------------------------------------------------------------
// Framer-motion animation variants
// ---------------------------------------------------------------------------

const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? "100%" : "-100%",
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? "-100%" : "100%",
    opacity: 0,
  }),
};

const reducedVariants = {
  enter: { opacity: 0 },
  center: { opacity: 1 },
  exit: { opacity: 0 },
};

// ---------------------------------------------------------------------------
// Entry choice — shown INSTEAD of the form when the wizard is fresh and
// prior plans exist: start from scratch, or copy every input from a chosen
// previous plan and tweak from there (issue #1).
// ---------------------------------------------------------------------------

function EntryChoice({
  households,
  onStartFresh,
  onCopyFrom,
}: {
  households: HouseholdSummary[];
  onStartFresh: () => void;
  onCopyFrom: (householdId: string) => void;
}) {
  const [selectedId, setSelectedId] = useState(households[0].household_id);

  function planLabel(h: HouseholdSummary): string {
    const name = h.nickname ?? `${h.state} — ${h.filing_status}`;
    return `${name} (${new Date(h.created_at).toLocaleDateString()})`;
  }

  return (
    <div
      className="max-w-xl mx-auto rounded-xl border border-border bg-card shadow-folio p-8 space-y-6"
      data-testid="wizard-entry-choice"
    >
      <div className="flex gap-3">
        <span className="mt-1 inline-block w-1 h-10 rounded-full bg-accent flex-shrink-0" aria-hidden="true" />
        <div>
          <h2 className="font-display text-xl font-semibold text-primary">
            Start your new plan
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Copy the inputs from a previous plan and change what you need,
            or begin with a blank form.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="copy-from-plan">
          Copy from
        </label>
        <Select value={selectedId} onValueChange={setSelectedId}>
          <SelectTrigger id="copy-from-plan">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {households.map((h) => (
              <SelectItem key={h.household_id} value={h.household_id}>
                {planLabel(h)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center justify-end gap-3">
        <Button variant="outline" onClick={onStartFresh}>
          Start fresh
        </Button>
        <Button onClick={() => onCopyFrom(selectedId)}>
          Copy this plan&apos;s inputs
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Draft resume banner
// ---------------------------------------------------------------------------

function DraftBanner({ onDismiss, onStartOver }: { onDismiss: () => void; onStartOver: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-accent/10 border border-accent/30 px-4 py-2.5 text-sm mb-4">
      <span className="text-foreground">
        Resuming your saved draft.
      </span>
      <div className="flex items-center gap-2 flex-shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-foreground h-7 px-2 text-xs"
          onClick={onStartOver}
        >
          Start over
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="text-accent hover:text-accent/80 h-7 px-2 text-xs"
          onClick={onDismiss}
        >
          Continue
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main wizard page
// ---------------------------------------------------------------------------

export default function WizardPage() {
  const step = useWizardStore((s) => s.step);
  const visitedMax = useWizardStore((s) => s.visitedMax);
  const data = useWizardStore((s) => s.data);
  const next = useWizardStore((s) => s.next);
  const back = useWizardStore((s) => s.back);
  const goToStep = useWizardStore((s) => s.goToStep);
  const clearDraft = useWizardStore((s) => s.clearDraft);
  const loadFrom = useWizardStore((s) => s.loadFrom);
  const resumePlan = useWizardStore((s) => s.resumePlan);
  const resume = useWizardStore((s) => s.resume);
  const claimModes = useWizardStore((s) => s.claimModes);

  const [showErrors, setShowErrors] = useState(false);
  const [resumeError, setResumeError] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Track direction of step change for animation
  const prevStep = useRef(step);
  const direction = useRef(1);
  useEffect(() => {
    direction.current = step > prevStep.current ? 1 : -1;
    prevStep.current = step;
  }, [step]);

  // Draft resume banner: show if there's a non-fresh draft (visitedMax > 0)
  const [showDraftBanner, setShowDraftBanner] = useState(false);
  const draftChecked = useRef(false);
  useEffect(() => {
    if (!draftChecked.current) {
      draftChecked.current = true;
      // After hydration, check if there's meaningful persisted state
      if (visitedMax > 0) {
        setShowDraftBanner(true);
      }
    }
  }, [visitedMax]);

  // Entry choice: on a fresh wizard (no draft) with prior plans, show an
  // explicit start-fresh vs copy-from-plan choice instead of the form.
  //
  // Three states, not two. Defaulting to "show the form and swap it out when
  // listHouseholds() comes back" rendered step 1 for the whole length of that
  // round-trip, so clicking New Plan flashed the profile form before landing
  // on this screen. We do not know which screen is right until the fetch
  // resolves, so say so rather than guessing and correcting.
  const [priorPlans, setPriorPlans] = useState<HouseholdSummary[]>([]);
  const [entryPhase, setEntryPhase] = useState<"deciding" | "form" | "choice">(
    "deciding",
  );
  const entryChecked = useRef(false);
  useEffect(() => {
    if (entryChecked.current) return;
    entryChecked.current = true;
    // ?resume=<id>: finish a saved plan that never completed a run (the
    // dashboard's "Finish setup and run"). A draft already resuming that plan
    // -- the user reloaded, or came back -- is kept; otherwise the plan is
    // loaded as saved, on Review.
    const resumeId = new URLSearchParams(window.location.search).get("resume");
    if (resumeId) {
      setShowDraftBanner(false);
      if (useWizardStore.getState().resume?.householdId === resumeId) {
        // Every step of a saved plan was completed once: all reachable.
        useWizardStore.setState((st) => ({
          visitedMax: LAST_STEP,
          step: st.visitedMax < LAST_STEP ? LAST_STEP : st.step,
        }));
        setEntryPhase("form");
        return;
      }
      getHousehold(resumeId)
        .then((detail) => resumePlan(detail, loadPlanModes(resumeId)))
        .catch(() => setResumeError(true))
        .finally(() => setEntryPhase("form"));
      return;
    }
    if (visitedMax > 0) {
      // Resuming a draft — the entry choice does not apply, and there is no
      // reason to hold the form behind a network call to establish that.
      setEntryPhase("form");
      return;
    }
    listHouseholds()
      .then((households) => {
        if (households.length > 0) {
          // Most recent first (API sorts by created_at DESC)
          setPriorPlans(households);
          setEntryPhase("choice");
        } else {
          setEntryPhase("form");
        }
      })
      .catch(() => {
        // Copying is a convenience, not a requirement — a backend that cannot
        // list plans must not block starting one.
        setEntryPhase("form");
      });
  }, [visitedMax]);

  async function handleCopyFrom(householdId: string) {
    try {
      const detail = await getHousehold(householdId);
      loadFrom(detail);
    } catch {
      // ignore — fall through to a fresh form
    }
    setEntryPhase("form");
  }

  const prefersReduced = useReducedMotion();

  function handleNext() {
    const { success, errors } = validateStep(step, data, claimModes);
    if (!success) {
      setShowErrors(true);
      setFieldErrors(errors);
      return;
    }
    setShowErrors(false);
    setFieldErrors({});
    next();
  }

  function handleBack() {
    setShowErrors(false);
    setFieldErrors({});
    back();
  }

  function handleRailClick(targetStep: number) {
    setShowErrors(false);
    setFieldErrors({});
    goToStep(targetStep);
  }

  // Discard the draft outright (localStorage included) rather than resetting
  // in memory — a stale balance or cost basis surviving a "start over" is
  // both confusing and a privacy leak on a shared machine.
  function handleStartOver() {
    clearDraft();
    setShowDraftBanner(false);
    setShowErrors(false);
    setFieldErrors({});
  }

  // "Start fresh" must actually be fresh.  loadFrom() sets visitedMax to 0, so
  // a copied plan's figures persist in the draft while the draft banner (and
  // its "Start over") stays hidden — leaving this screen as the ONLY exit, and
  // it used to dismiss the chooser without clearing anything.
  function handleStartFresh() {
    clearDraft();
    setEntryPhase("form");
  }

  const StepComponent = STEP_COMPONENTS[step] ?? StepProfile;
  const isLastStep = step === LAST_STEP;
  const isFirstStep = step === 0;

  const variants = prefersReduced ? reducedVariants : slideVariants;
  const transition = { duration: 0.2, ease: "easeOut" as const };

  // Still establishing which screen belongs here. Rendering the form now and
  // correcting it a moment later is what caused the flash, so hold the layout
  // instead — shaped like the entry choice, which is where a returning user
  // with saved plans is headed.
  if (entryPhase === "deciding") {
    return (
      <main className="min-h-screen bg-background">
        <div className="max-w-5xl mx-auto px-4 py-16">
          <div
            data-testid="wizard-entry-loading"
            aria-busy="true"
            aria-label="Preparing your new plan"
            className="max-w-xl mx-auto rounded-xl border border-border bg-card shadow-folio p-8 space-y-6"
          >
            <div className="h-7 w-2/3 rounded bg-muted animate-pulse" />
            <div className="h-4 w-full rounded bg-muted animate-pulse" />
            <div className="h-10 w-full rounded bg-muted animate-pulse" />
            <div className="h-10 w-40 rounded bg-muted animate-pulse" />
          </div>
        </div>
      </main>
    );
  }

  // Fresh wizard + prior plans → the entry choice replaces the form entirely
  // until the user picks start-fresh or copy-from (issue #1).
  if (entryPhase === "choice" && !showDraftBanner) {
    return (
      <main className="min-h-screen bg-background">
        <div className="max-w-5xl mx-auto px-4 py-16">
          <EntryChoice
            // Newest 10 only — the list is sorted newest-first and grows
            // with every what-if copy; delete stale plans to curate it
            households={priorPlans.slice(0, 10)}
            onStartFresh={handleStartFresh}
            onCopyFrom={handleCopyFrom}
          />
        </div>
      </main>
    );
  }

  return (
    <WizardErrorContext.Provider value={{ showErrors, errors: fieldErrors }}>
      <main className="min-h-screen bg-background">
        <div className="max-w-5xl mx-auto px-4 py-8">
          {resume && step === LAST_STEP && (
            <div
              className="rounded-md bg-accent/10 border border-accent/30 px-4 py-2.5 text-sm mb-4"
              data-testid="resume-banner"
            >
              Finishing setup for <strong>{data.household.nickname || "this saved plan"}</strong>.
              Running it uses this saved plan; it is not saved again.
            </div>
          )}
          {resumeError && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2.5 text-sm mb-4 text-destructive" role="alert">
              Couldn&apos;t load that saved plan. It may have been deleted.
            </div>
          )}
          {/* Draft banner */}
          {showDraftBanner && !resume && (
            <DraftBanner
              onDismiss={() => setShowDraftBanner(false)}
              onStartOver={handleStartOver}
            />
          )}

          {/* Progress rail */}
          <div className="mb-8">
            <ProgressRail
              step={step}
              visitedMax={visitedMax}
              onStepClick={handleRailClick}
            />
          </div>

          {/* Two-column layout: form panel (2/3) + summary aside (1/3) */}
          <div className="flex flex-col lg:grid lg:grid-cols-3 lg:gap-6 gap-6">
            {/* Main form panel; centred on Review, which has no side summary */}
            <div className={isLastStep ? "lg:col-span-3 lg:w-2/3 lg:mx-auto" : "lg:col-span-2"}>
              <div className="rounded-xl border border-border bg-card shadow-folio overflow-hidden">
                {/* Animated step content */}
                <div className="relative overflow-hidden">
                  <AnimatePresence
                    mode="wait"
                    custom={direction.current}
                    initial={false}
                  >
                    <motion.div
                      key={step}
                      custom={direction.current}
                      variants={variants}
                      initial="enter"
                      animate="center"
                      exit="exit"
                      transition={transition}
                      className="p-6"
                    >
                      <StepComponent />
                    </motion.div>
                  </AnimatePresence>
                </div>

                {/* Validation fallback: even if a failing field has no
                    inline slot (or isn't rendered), a blocked Next/Review
                    must never be silent. */}
                {showErrors && Object.keys(fieldErrors).length > 0 && (
                  <div
                    className="mx-6 mb-2 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2.5 text-sm text-destructive"
                    role="alert"
                    data-testid="step-error-summary"
                  >
                    <p className="font-medium">Please fix before continuing:</p>
                    <ul className="list-disc pl-5 mt-1 space-y-0.5">
                      {Object.entries(fieldErrors).map(([field, msg]) => (
                        <li key={field}>
                          {errorPlace(field)}: {msg}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Back / Next footer — hidden on the final step (Review has its own submit) */}
                {!isLastStep && (
                  <div
                    className={cn(
                      "flex justify-between items-center gap-2 px-6 py-4",
                      "border-t border-border bg-muted/20"
                    )}
                  >
                    {!isFirstStep ? (
                      <Button
                        variant="outline"
                        onClick={handleBack}
                        className="min-w-[80px]"
                      >
                        Back
                      </Button>
                    ) : (
                      <span />
                    )}

                    <Button
                      onClick={handleNext}
                      className={cn(
                        "min-w-[80px]",
                        "bg-primary text-primary-foreground hover:bg-secondary"
                      )}
                    >
                      {step === LAST_STEP - 1 ? "Review" : "Next"}
                    </Button>
                  </div>
                )}

                {/* Back button on the final step */}
                {isLastStep && (
                  <div className="flex justify-start px-6 py-4 border-t border-border bg-muted/20">
                    <Button
                      variant="outline"
                      onClick={handleBack}
                      className="min-w-[80px]"
                    >
                      Back
                    </Button>
                  </div>
                )}
              </div>
            </div>

            {/* Summary aside — sticky on lg screens, stacks below on mobile */}
            {/* On Review the step's own summary replaces it: one summary, not two. */}
            {!isLastStep && (
              <div className="lg:col-span-1">
                <div className="lg:sticky lg:top-8">
                  <SummaryAside />
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </WizardErrorContext.Provider>
  );
}

const ROW_FIELD_NAMES: Record<string, string> = { roth_opened_year: "year Roth opened" };

/** Where an error sits, in words: "Account 3 · year Roth opened". */
function errorPlace(field: string): string {
  const m = field.match(/^(accounts|income)\.(\d+)\.(.+)$/);
  if (!m) return field.replace(/[._]/g, " ");
  const what = m[1] === "accounts" ? "Account" : "Income source";
  return `${what} ${Number(m[2]) + 1} · ${ROW_FIELD_NAMES[m[3]] ?? m[3].replace(/[._]/g, " ")}`;
}
