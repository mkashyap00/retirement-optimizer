"use client";

import { useContext } from "react";
import { useWizardStore } from "@/stores/wizardStore";
import { AdornedInput } from "@/components/ui/currency-input";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { WizardErrorContext } from "../WizardContext";
import { IRMAA_CHOICES, irmaaChoice } from "@/lib/labels";
import { FieldLabel, InfoTip, FieldError, StepHeader } from "./shared";

const IRMAA_TIP =
  "IRMAA (Income-Related Monthly Adjustment Amount) is a surcharge on Medicare Part B and " +
  "Part D premiums for people whose income is above set thresholds. It is based on your " +
  "income from two years earlier, so a Roth conversion at 63 or later can raise premiums. " +
  "It works as a cliff: going $1 over a threshold adds that tier's full surcharge for the " +
  "year, for each person on Medicare — it does not phase in.";

/** Percent input — stores decimal (0.03), displays percentage (3). */
function PercentInput({
  id,
  value,
  onChange,
}: {
  id?: string;
  value: number | undefined;
  onChange: (n: number) => void;
}) {
  const displayVal = value != null ? parseFloat((value * 100).toFixed(10)) : "";

  return (
    <AdornedInput
      id={id}
      type="number"
      step="0.1"
      min={0}
      max={100}
      suffix="%"
      value={displayVal}
      onChange={(e) => {
        const display = parseFloat(e.target.value);
        onChange(isNaN(display) ? 0 : display / 100);
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Step 2: Planning Assumptions
// ---------------------------------------------------------------------------

const WINDOW_OPTIONS = [
  { value: "anytime", label: "Anytime" },
  { value: "pre_medicare", label: "Before Medicare (65)" },
  { value: "pre_rmd", label: "Before RMDs (73, or 75 if born 1960+)" },
  { value: "pre_ss", label: "Before Social Security" },
] as const;

export function StepAssumptions() {
  const data = useWizardStore((s) => s.data);
  const setField = useWizardStore((s) => s.setField);
  const { showErrors, errors } = useContext(WizardErrorContext);

  return (
    <div>
      <StepHeader
        title="Planning Assumptions"
        description="Set the economic assumptions and constraints for optimization."
      />

      <div className="flex flex-col gap-4">
        {/* Inflation Rate */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="inflation"
            tip="Rate at which your spending needs grow each year. The optimizer adjusts required spending upward by this amount annually."
          >
            Inflation Rate
          </FieldLabel>
          <PercentInput
            id="inflation"
            value={data.settings.inflation}
            onChange={(v) => setField("settings.inflation", v)}
          />
          {showErrors && errors["inflation"] && (
            <FieldError message={errors["inflation"]} />
          )}
        </div>

        {/* Nominal Return */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="nominal-return"
            tip="Expected annual return on your portfolio before subtracting inflation. Used to project balances forward."
          >
            Nominal Return
          </FieldLabel>
          <PercentInput
            id="nominal-return"
            value={data.settings.nominal_return}
            onChange={(v) => setField("settings.nominal_return", v)}
          />
          {showErrors && errors["nominal_return"] && (
            <FieldError message={errors["nominal_return"]} />
          )}
        </div>

        {/* Settings most plans keep at their defaults, always shown so none
            is missed. */}
        <section className="rounded-lg border border-border px-4 py-3" data-testid="advanced-assumptions">
          <h3 className="text-sm font-medium text-foreground">Advanced settings</h3>
          <div className="mt-4 flex flex-col gap-4">
        {/* Heir Tax Rate */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="heir-tax-rate"
            tip="Marginal income-tax rate your heirs would pay on an inherited traditional IRA (they must empty it within 10 years). A traditional dollar counts as (1 − this rate) in the estate score, so a higher rate makes Roth conversions more attractive."
          >
            Heir Tax Rate
          </FieldLabel>
          <PercentInput
            id="heir-tax-rate"
            value={data.settings.heir_tax_rate ?? 0.25}
            onChange={(v) => setField("settings.heir_tax_rate", v)}
          />
        </div>

        {/* Medicare surcharge (IRMAA): two behaviours, so two choices. An
            older plan's ignore/avoid shows as the choice it behaves as and
            is saved unchanged unless the user picks again. */}
        <fieldset className="flex flex-col gap-1.5" data-testid="irmaa-policy">
          <legend className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
            Medicare surcharge thresholds (IRMAA)
            <InfoTip text={IRMAA_TIP} />
          </legend>
          {IRMAA_CHOICES.map((opt) => (
            <label key={opt.value} className="flex items-start gap-2 text-sm cursor-pointer">
              <input
                type="radio"
                name="irmaa-policy"
                value={opt.value}
                checked={irmaaChoice(data.constraints.irmaa_policy) === opt.value}
                onChange={() => setField("constraints.irmaa_policy", opt.value)}
                className="mt-1"
                data-testid={`irmaa-${opt.value}`}
              />
              <span>
                {opt.label}
                <span className="block text-xs text-muted-foreground">{opt.description}</span>
              </span>
            </label>
          ))}
        </fieldset>

        {/* Conversion Window */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="conversion-window"
            tip="Restricts Roth conversions to a specific period. 'Anytime' places no restriction."
          >
            Conversion Window
          </FieldLabel>
          <ToggleGroup
            type="single"
            id="conversion-window"
            value={data.constraints.conversion_window}
            onValueChange={(val) => {
              if (val) setField("constraints.conversion_window", val);
            }}
            className="flex-wrap"
          >
            {WINDOW_OPTIONS.map((opt) => (
              <ToggleGroupItem key={opt.value} value={opt.value}>
                {opt.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>

        {/* Preserve Taxable */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="preserve-taxable"
            tip="OFF (default): spend taxable brokerage first — capital-gains rates (0/15/20%) usually beat ordinary rates on IRA withdrawals. ON: spend the traditional IRA first instead — an estate strategy: heirs inherit taxable assets with a step-up in basis (gains erased), while inherited IRAs are fully taxable to them; drawing the IRA early also shrinks future RMDs."
          >
            Preserve Taxable Accounts
          </FieldLabel>
          <div className="flex items-center gap-2">
            <Switch
              id="preserve-taxable"
              checked={data.constraints.preserve_taxable}
              onCheckedChange={(v) =>
                setField("constraints.preserve_taxable", v)
              }
            />
            <span className="text-xs text-muted-foreground">
              {data.constraints.preserve_taxable
                ? "IRA drawn first — taxable kept for heirs (basis step-up)"
                : "Taxable drawn first (default — lower capital-gains rates)"}
            </span>
          </div>
        </div>
          </div>
        </section>
      </div>
    </div>
  );
}
