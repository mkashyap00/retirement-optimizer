"use client";

import { useContext, useEffect, useState } from "react";
import { Trash2, Plus } from "lucide-react";
import { useWizardStore } from "@/stores/wizardStore";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { AdornedInput, CurrencyInput } from "@/components/ui/currency-input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ClaimAgeSetup } from "@/components/ClaimAgeSetup";
import { useClaimPreview } from "@/lib/useClaimPreview";
import { type ClaimMode, type PersonPreview } from "@/lib/claimSetup";
import { WizardErrorContext } from "../WizardContext";
import { cn } from "@/lib/utils";
import { yearSpan } from "@/lib/labels";
import { hasCapitalGains, noCapitalGains } from "@/lib/capitalGains";
import type { CapitalGainsIn } from "@/lib/types";
import {
  FieldLabel,
  FieldError,
  StepHeader,
  useCollapsed,
  money,
  EntrySummary,
  claimPreviewBody,
} from "./shared";

/** Optional percent input — blank stores null (use the default), a number
 *  stores a decimal (2.5 -> 0.025). */
function OptionalPercentInput({
  id,
  value,
  placeholder,
  onChange,
}: {
  id?: string;
  value: number | null | undefined;
  placeholder?: string;
  onChange: (n: number | null) => void;
}) {
  const displayVal = value != null ? parseFloat((value * 100).toFixed(10)) : "";

  return (
    <AdornedInput
      id={id}
      type="number"
      step="0.1"
      min={0}
      max={20}
      suffix="%"
      placeholder={placeholder}
      value={displayVal}
      onChange={(e) => {
        if (e.target.value.trim() === "") {
          onChange(null);
          return;
        }
        const display = parseFloat(e.target.value);
        onChange(isNaN(display) ? null : display / 100);
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Step 4: Income & Social Security
// ---------------------------------------------------------------------------

/** Age reached this calendar year (as the optimizer counts it), or null. */
export function ageThisYear(birthDate: string | undefined | null): number | null {
  if (!birthDate || birthDate.length < 4) return null;
  return new Date().getFullYear() - Number(birthDate.slice(0, 4));
}

/** "Already receiving benefits?" as an explicit Yes / No. Unanswered stays
 *  unanswered (null) -- a plan saved before the question existed must not be
 *  read as "No". Only asked from 62, the earliest claim age. */
function ReceivingQuestion({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: boolean | null | undefined;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground" id={`${id}-label`}>
        {label}
      </span>
      <ToggleGroup
        type="single"
        id={id}
        aria-labelledby={`${id}-label`}
        value={value == null ? "" : value ? "yes" : "no"}
        onValueChange={(v) => {
          if (v) onChange(v === "yes");
        }}
        className="justify-start"
      >
        <ToggleGroupItem value="yes" data-testid={`${id}-yes`}>Yes</ToggleGroupItem>
        <ToggleGroupItem value="no" data-testid={`${id}-no`}>No</ToggleGroupItem>
      </ToggleGroup>
      {value == null && (
        <span className="text-xs text-amber-700">Not answered yet</span>
      )}
    </div>
  );
}

export function StepIncomeAndSS() {
  const data = useWizardStore((s) => s.data);
  const setField = useWizardStore((s) => s.setField);
  const addIncome = useWizardStore((s) => s.addIncome);
  const removeIncome = useWizardStore((s) => s.removeIncome);
  const { showErrors, errors } = useContext(WizardErrorContext);

  const income = data.income;
  const isJoint = data.household.filing_status === "joint";
  const incomeRows = useCollapsed(() =>
    income.flatMap((inc, i) => ((inc.amount ?? 0) > 0 ? [i] : [])));
  const incomeComplete = (i: number) =>
    (income[i].amount ?? 0) > 0 &&
    !(showErrors && Object.keys(errors).some((k) => k.startsWith(`income.${i}.`)));
  const INCOME_NAMES: Record<string, string> = {
    salary: "salary", pension: "pension", rental: "rental income", interest: "interest",
    qualified_dividend: "qualified dividends", nonqualified_dividend: "non-qualified dividends",
  };
  const claimModes = useWizardStore((s) => s.claimModes);
  const chooseMode = useWizardStore((s) => s.chooseMode);
  const unconfirmed = useWizardStore((s) => s.unconfirmedModes);
  const claim = useClaimPreview({ body: claimPreviewBody(data) });
  const selfAge = ageThisYear(data.household.self_birth_date);
  const spouseAge = ageThisYear(data.household.spouse_birth_date);

  return (
    <div>
      <StepHeader
        title="Income & Social Security"
        description="Add income sources and Social Security benefit information."
      />

      <div className="flex flex-col gap-4">
        {/* Income sources */}
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">
            Income Sources
          </h3>

          {income.map((inc, i) => incomeComplete(i) && incomeRows.isCollapsed(i) ? (
            <EntrySummary
              key={i}
              testId={`income-summary-${i}`}
              what={`income ${i + 1}`}
              text={(() => {
                // "Your salary · $100,000/year · 2026–2028"
                const whose = inc.owner === "spouse" ? "Spouse's" : inc.owner === "joint" ? "Joint" : "Your";
                const span = yearSpan(inc.start_year, inc.end_year);
                return `${whose} ${INCOME_NAMES[inc.category] ?? inc.category} · ${money(inc.amount)}/year${span ? ` · ${span}` : ""}`;
              })()}
              onEdit={() => incomeRows.expand(i)}
              onRemove={() => {
                incomeRows.removed(i);
                removeIncome(i);
              }}
            />
          ) : (
            <div
              key={i}
              className="rounded-lg border border-border bg-card p-4 shadow-folio flex flex-col gap-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Income {i + 1}
                </span>
                <span className="flex gap-1 -mr-1">
                  {incomeComplete(i) && (
                    <Button variant="ghost" size="sm" onClick={() => incomeRows.collapse(i)}>
                      Done
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      incomeRows.removed(i);
                      removeIncome(i);
                    }}
                    aria-label={`Remove income ${i + 1}`}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="w-3.5 h-3.5 mr-1" />
                    Remove
                  </Button>
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {/* Category */}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`inc-cat-${i}`}>Category</Label>
                  <Select
                    value={inc.category}
                    onValueChange={(val) =>
                      setField(`income.${i}.category`, val)
                    }
                  >
                    <SelectTrigger id={`inc-cat-${i}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="salary">Salary</SelectItem>
                      <SelectItem value="pension">Pension</SelectItem>
                      <SelectItem value="rental">Rental</SelectItem>
                      <SelectItem value="interest">Interest</SelectItem>
                      <SelectItem value="qualified_dividend">Qualified Dividends</SelectItem>
                      <SelectItem value="nonqualified_dividend">Non-Qualified Dividends</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Owner */}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`inc-owner-${i}`}>Owner</Label>
                  <Select
                    value={inc.owner}
                    onValueChange={(val) =>
                      setField(`income.${i}.owner`, val)
                    }
                  >
                    <SelectTrigger id={`inc-owner-${i}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="self">Self</SelectItem>
                      {isJoint && (
                        <SelectItem value="spouse">Spouse</SelectItem>
                      )}
                      {isJoint && (
                        <SelectItem value="joint">Joint</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>

                {/* Amount */}
                <div className="flex flex-col gap-1.5">
                  <FieldLabel
                    htmlFor={`inc-amount-${i}`}
                    tip="Annual income amount. For temporary income, set start and end years."
                  >
                    Annual Amount
                  </FieldLabel>
                  <CurrencyInput
                    id={`inc-amount-${i}`}
                    value={inc.amount}
                    onChange={(n) =>
                      setField(`income.${i}.amount`, n ?? 0)
                    }
                  />
                </div>

                {/* Start Year */}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`inc-start-${i}`}>Start Year</Label>
                  <Input
                    id={`inc-start-${i}`}
                    type="number"
                    min={new Date().getFullYear()}
                    max={2100}
                    placeholder={`e.g. ${new Date().getFullYear()}`}
                    value={inc.start_year ?? ""}
                    onChange={(e) =>
                      setField(
                        `income.${i}.start_year`,
                        e.target.value === ""
                          ? undefined
                          : Number(e.target.value)
                      )
                    }
                  />
                </div>

                {/* End Year */}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`inc-end-${i}`}>End Year</Label>
                  <Input
                    id={`inc-end-${i}`}
                    type="number"
                    min={new Date().getFullYear()}
                    max={2100}
                    placeholder={`e.g. ${new Date().getFullYear() + 9}`}
                    value={inc.end_year ?? ""}
                    onChange={(e) =>
                      setField(
                        `income.${i}.end_year`,
                        e.target.value === ""
                          ? undefined
                          : Number(e.target.value)
                      )
                    }
                  />
                </div>
              </div>
            </div>
          ))}

          <Button
            variant="outline"
            onClick={addIncome}
            className="w-full border-dashed text-muted-foreground hover:text-foreground hover:border-primary"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Income Source
          </Button>
        </div>

        <RealizedGains />

        {/* Social Security: per person, the order a person decides in --
            already receiving? then how to choose the age, then the age. */}
        <div className="rounded-lg border border-border bg-card p-4 shadow-folio">
          <h3 className="text-sm font-semibold text-foreground mb-3">
            Social Security
          </h3>

          <div className={cn("grid gap-6", isJoint && "md:grid-cols-2")}>
            <PersonSocialSecurity
              who="self"
              age={selfAge}
              preview={claim.preview?.self ?? null}
              mode={unconfirmed.includes("self") ? null : claimModes.self}
              onMode={(m) => chooseMode("self", m)}
            />
            {isJoint && (
              <PersonSocialSecurity
                who="spouse"
                age={spouseAge}
                preview={claim.preview?.spouse ?? null}
                mode={unconfirmed.includes("spouse") ? null : claimModes.spouse}
                onMode={(m) => chooseMode("spouse", m)}
              />
            )}
          </div>

          {/* Projected COLA — blank follows the inflation assumption */}
          <div className="flex flex-col gap-1.5 mt-5">
            <FieldLabel
              htmlFor="ss-cola"
              tip="How fast Social Security benefits grow each year. Enter your PIA in today's dollars; the benefit then grows by this rate every year, before and after claiming. Leave blank to use your inflation assumption. Enter 0 to hold benefits flat."
            >
              Social Security COLA
            </FieldLabel>
            <OptionalPercentInput
              id="ss-cola"
              value={data.settings.ss_cola}
              placeholder={`Same as inflation (${(data.settings.inflation * 100).toFixed(1)}%)`}
              onChange={(v) => setField("settings.ss_cola", v)}
            />
          </div>

          {/* What these choices will run, with the backend's own eligibility
              (the same rules the search applies). */}
          <div className="mt-4 border-t border-border pt-4">
            <h4 className="text-sm font-semibold text-foreground mb-2">What the run will compare</h4>
            <ClaimAgeSetup
              preview={claim.preview}
              modes={claimModes}
              loading={claim.loading}
              error={claim.error}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Capital gains already realized this year, and the loss carried into it.
 *  They change this year's tax only: the sale proceeds are already in the
 *  balances entered on Accounts, so they are never added as cash. */
function RealizedGains() {
  const stored = useWizardStore((s) => s.data.capital_gains);
  const setField = useWizardStore((s) => s.setField);
  const thisYear = new Date().getFullYear();
  // A blank entry left from an earlier year (a draft kept past New Year) is
  // simply this year's. Figures entered for an earlier year keep their year
  // -- never silently relabelled -- until the user starts this year's.
  const gains = hasCapitalGains(stored) ? stored : noCapitalGains();
  const year = gains.tax_year;
  const set = (field: keyof CapitalGainsIn, v: number) =>
    hasCapitalGains(stored)
      ? setField(`capital_gains.${field}`, v)
      : setField("capital_gains", { ...noCapitalGains(), [field]: v });
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-folio" data-testid="realized-gains">
      <h3 className="text-sm font-semibold text-foreground" data-testid="realized-gains-title">
        Investment gains already realized in {year}
      </h3>
      {year < thisYear && (
        <div className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
          data-testid="realized-gains-stale">
          These figures are for {year}, which is over; a plan starting in {thisYear} does not
          apply them.{" "}
          <button
            type="button"
            className="underline underline-offset-2 font-medium"
            onClick={() => setField("capital_gains", noCapitalGains())}
          >
            Start {thisYear} entries
          </button>
        </div>
      )}
      <p className="text-xs text-muted-foreground mt-1 mb-3">
        Enter gains from investments you have already sold this year — not the total sale
        proceeds or gains on investments you still own. Use the net amount: gains minus losses
        so far. Mutual fund capital gain distributions count as long-term. These change{" "}
        {year}&apos;s tax only; the money from the sales is already in the balances you entered,
        so it is not counted again.
      </p>
      {/* Keyed by year so starting a new year's entries resets each toggle. */}
      <div className="grid gap-4 md:grid-cols-2" key={year}>
        <GainOrLoss
          id="gain-st"
          label="Short-term (held one year or less)"
          tip="Taxed as ordinary income, so it uses up the bracket room a Roth conversion would otherwise fill."
          value={gains.short_term}
          onChange={(v) => set("short_term", v)}
        />
        <GainOrLoss
          id="gain-lt"
          label="Long-term (held more than one year)"
          tip="Taxed at capital-gains rates on top of ordinary income. A conversion can push more of it into the 15% or 20% rate, and raise the 3.8% investment income tax."
          value={gains.long_term}
          onChange={(v) => set("long_term", v)}
        />
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="carry-st"
            tip={`From your ${year - 1} return: the short-term capital loss carryover (Capital Loss Carryover Worksheet in the Schedule D instructions). Leave blank if none.`}
          >
            Short-term loss carried over from {year - 1}
          </FieldLabel>
          <CurrencyInput
            id="carry-st"
            value={gains.carryover_short_term}
            onChange={(n) => set("carryover_short_term", n ?? 0)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="carry-lt"
            tip={`From your ${year - 1} return: the long-term capital loss carryover. Leave blank if none.`}
          >
            Long-term loss carried over from {year - 1}
          </FieldLabel>
          <CurrencyInput
            id="carry-lt"
            value={gains.carryover_long_term}
            onChange={(n) => set("carryover_long_term", n ?? 0)}
          />
        </div>
      </div>
    </div>
  );
}

/** A net amount that may be a gain or a loss: the amount, and which it is.
 *  Stored signed (a loss is negative). */
function GainOrLoss({
  id, label, tip, value, onChange,
}: {
  id: string;
  label: string;
  tip: string;
  value: number;
  onChange: (v: number) => void;
}) {
  // The sign is kept apart from the amount so "Loss" survives a blank amount.
  const [loss, setLoss] = useState(value < 0);
  const amount = Math.abs(value ?? 0);
  return (
    <div className="flex flex-col gap-1.5">
      <FieldLabel htmlFor={id} tip={tip}>{label}</FieldLabel>
      <div className="flex gap-2 items-center">
        <div className="flex-1">
          {/* The toggle alone sets the sign: the amount is always read as
              a magnitude, so a typed "-10,000" under Loss stays a loss. */}
          <CurrencyInput
            id={id}
            value={amount}
            onChange={(n) => onChange((loss ? -1 : 1) * Math.abs(n ?? 0))}
          />
        </div>
        <ToggleGroup
          type="single"
          value={loss ? "loss" : "gain"}
          onValueChange={(v) => {
            if (!v) return;
            setLoss(v === "loss");
            onChange((v === "loss" ? -1 : 1) * amount);
          }}
          aria-label={`${label}: gain or loss`}
        >
          <ToggleGroupItem value="gain" data-testid={`${id}-gain`}>Gain</ToggleGroupItem>
          <ToggleGroupItem value="loss" data-testid={`${id}-loss`}>Loss</ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>
  );
}

/** Age options from *lo* to *hi*, as Select items. */
function ageItems(lo: number, hi: number) {
  return Array.from({ length: Math.max(0, hi - lo + 1) }, (_, i) => String(lo + i));
}

const SS_TEXT = {
  self: {
    legend: "You",
    pia: "Your monthly benefit at full retirement age",
    piaTip: "Your Social Security benefit at full retirement age — your PIA (primary insurance amount). Log in at ssa.gov/myaccount and look under 'At your full retirement age.' Enter that figure, not the early or delayed amounts: the optimizer works out the benefit at each claim age. Enter 0 if you have no work record of your own (a spousal benefit can still apply).",
    receiving: "Already receiving Social Security?",
    how: "How should we choose your claim age?",
  },
  spouse: {
    legend: "Spouse",
    pia: "Spouse's monthly benefit at full retirement age",
    piaTip: "Your spouse's Social Security benefit at full retirement age (their PIA) — find it at ssa.gov/myaccount. Enter 0 if they have no work record of their own.",
    receiving: "Spouse already receiving Social Security?",
    how: "How should we choose your spouse's claim age?",
  },
} as const;

/** One person's Social Security questions, each shown once the one before
 *  it is answered: the benefit; already receiving (from 62); if so, the age
 *  it started (fixed); if not, whether the optimizer finds the age or the
 *  user chooses it -- and only then an age selector. A searched age may
 *  carry an optional comparison age; none is invented when it is blank. */
function PersonSocialSecurity({
  who,
  age,
  preview,
  mode,
  onMode,
}: {
  who: "self" | "spouse";
  age: number | null;
  preview: PersonPreview | null;
  /** null: not yet chosen (a resumed plan whose choice was not recorded). */
  mode: ClaimMode | null;
  onMode: (m: ClaimMode) => void;
}) {
  const data = useWizardStore((s) => s.data);
  const setField = useWizardStore((s) => s.setField);
  const { showErrors, errors } = useContext(WizardErrorContext);
  const t = SS_TEXT[who];
  const piaKey = `ss_pia_${who}` as const;
  const claimKey = `ss_claim_age_${who}` as const;
  const receivingKey = `ss_receiving_${who}` as const;
  const pia = data.settings[piaKey];
  const claim = data.settings[claimKey] ?? null;
  const receiving = data.settings[receivingKey] ?? null;
  const setClaim = (v: number | null) => setField(`settings.${claimKey}`, v);
  const asked = age != null && age >= 62;
  const over70 = age != null && age >= 70 && receiving === false;
  const deciding = pia != null && receiving !== true && !over70 && (!asked || receiving === false);
  const earliest = Math.max(62, age ?? 62);

  // Over 70 and not yet filed: modelled as filing now, at the age-70 benefit.
  useEffect(() => {
    if (over70 && claim !== 70) setClaim(70);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [over70, claim]);

  function answerReceiving(v: boolean) {
    setField(`settings.${receivingKey}`, v);
    // Keep an age that still fits the answer; one that cannot (a past age
    // as a plan, a future one as a claim already made) is cleared.
    if (claim != null && age != null && (v ? claim > age : claim < Math.min(age, 70))) setClaim(null);
  }

  const err = (k: string) => showErrors && errors[k] ? <FieldError message={errors[k]} /> : null;
  const searchable = preview?.status === "searchable" && preview.ages.length > 1;

  return (
    <fieldset className="flex flex-col gap-3" data-testid={`ss-person-${who}`}>
      <legend className="text-sm font-semibold text-foreground">{t.legend}</legend>
      <div className="flex flex-col gap-1.5">
        <FieldLabel htmlFor={`ss-pia-${who}`} tip={t.piaTip}>{t.pia}</FieldLabel>
        <CurrencyInput
          id={`ss-pia-${who}`}
          value={pia ?? undefined}
          onChange={(n) => setField(`settings.${piaKey}`, n ?? 0)}
        />
        {err(piaKey)}
      </div>

      {asked && pia != null && (
        <>
          <ReceivingQuestion
            id={`ss-receiving-${who}`}
            label={t.receiving}
            value={receiving}
            onChange={answerReceiving}
          />
          {err(receivingKey)}
        </>
      )}

      {receiving === true && age != null && (
        <div className="flex flex-col gap-1.5">
          <FieldLabel htmlFor={`ss-age-${who}`}>At what age did benefits start?</FieldLabel>
          <Select
            value={claim != null ? String(claim) : ""}
            onValueChange={(v) => setClaim(Number(v))}
          >
            <SelectTrigger id={`ss-age-${who}`}>
              <SelectValue placeholder="Choose an age" />
            </SelectTrigger>
            <SelectContent>
              {ageItems(62, Math.min(age, 70)).map((a) => (
                <SelectItem key={a} value={a}>{a}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">A claim already made stays fixed.</p>
          {err(claimKey)}
        </div>
      )}

      {over70 && (
        <p className="text-xs text-muted-foreground">
          Over 70 and not yet receiving: modelled as filing this year, at the age-70 benefit.
        </p>
      )}

      {deciding && (
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium" id={`claim-mode-${who}-label`}>{t.how}</span>
          <div role="radiogroup" aria-labelledby={`claim-mode-${who}-label`} className="flex flex-col gap-1.5">
            {([
              ["search", "Find the best eligible age"],
              ["fixed", "Use an age I choose"],
            ] as const).map(([value, text]) => (
              <label key={value} className="flex items-start gap-2 text-sm cursor-pointer">
                <input
                  type="radio"
                  name={`claim-mode-${who}`}
                  value={value}
                  checked={mode === value}
                  onChange={() => onMode(value)}
                  className="mt-1"
                  data-testid={`claim-mode-${who}-${value}`}
                />
                <span>
                  {text}
                  {value === "search" && searchable && (
                    <span className="block text-xs text-muted-foreground">
                      Tries ages {Math.min(...preview!.ages)}–{Math.max(...preview!.ages)}
                    </span>
                  )}
                </span>
              </label>
            ))}
          </div>

          {mode === "fixed" && (
            <div className="flex flex-col gap-1.5">
              <FieldLabel
                htmlFor={`ss-age-${who}`}
                tip="Claiming before full retirement age permanently reduces the benefit; delaying increases it up to 70."
              >
                Claim age
              </FieldLabel>
              <Select value={claim != null ? String(claim) : ""} onValueChange={(v) => setClaim(Number(v))}>
                <SelectTrigger id={`ss-age-${who}`}>
                  <SelectValue placeholder="Choose an age" />
                </SelectTrigger>
                <SelectContent>
                  {ageItems(earliest, 70).map((a) => (
                    <SelectItem key={a} value={a}>{a}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {err(claimKey)}
            </div>
          )}

          {mode === "search" && (
            <>
              {preview && preview.exclusions.length > 0 && (
                <ul className="text-xs text-muted-foreground list-disc pl-5" data-testid={`claim-exclusions-${who}`}>
                  {preview.exclusions.map((e) => (
                    <li key={e.age}>Age {e.age} skipped: {e.reason}</li>
                  ))}
                </ul>
              )}
              <div className="flex flex-col gap-1.5 rounded-md bg-muted/30 p-3">
                <Label htmlFor={`ss-compare-${who}`}>
                  Have a claim age in mind?{" "}
                  <span className="text-muted-foreground font-normal">(optional)</span>
                </Label>
                <p className="text-xs text-muted-foreground">
                  We&apos;ll compare the recommendation with your choice.
                </p>
                <Select
                  value={claim != null ? String(claim) : "none"}
                  onValueChange={(v) => setClaim(v === "none" ? null : Number(v))}
                >
                  <SelectTrigger id={`ss-compare-${who}`} data-testid={`ss-compare-${who}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No comparison</SelectItem>
                    {ageItems(earliest, 70).map((a) => (
                      <SelectItem key={a} value={a}>{a}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {preview && claim != null && preview.status === "searchable" && !preview.ages.includes(claim) && (
                  <p className="text-xs text-amber-700">
                    Age {claim} is skipped in the search; it is still scored for the comparison
                    but cannot be recommended.
                  </p>
                )}
                {err(claimKey)}
              </div>
            </>
          )}
        </div>
      )}
    </fieldset>
  );
}
