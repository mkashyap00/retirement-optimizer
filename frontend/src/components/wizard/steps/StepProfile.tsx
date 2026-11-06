"use client";

import { useContext } from "react";
import { useWizardStore } from "@/stores/wizardStore";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { WizardErrorContext } from "../WizardContext";
import { cn } from "@/lib/utils";
import { DEFAULT_PLAN_THROUGH_AGE, projectionEndYear } from "@/lib/planHorizon";
import { householdHorizon } from "@/lib/planPayload";
import { FieldLabel, FieldError, StepHeader } from "./shared";

// ---------------------------------------------------------------------------
// US States
// ---------------------------------------------------------------------------

const US_STATES = [
  { value: "AL", label: "Alabama" },
  { value: "AK", label: "Alaska" },
  { value: "AZ", label: "Arizona" },
  { value: "AR", label: "Arkansas" },
  { value: "CA", label: "California" },
  { value: "CO", label: "Colorado" },
  { value: "CT", label: "Connecticut" },
  { value: "DC", label: "District of Columbia" },
  { value: "DE", label: "Delaware" },
  { value: "FL", label: "Florida" },
  { value: "GA", label: "Georgia" },
  { value: "HI", label: "Hawaii" },
  { value: "ID", label: "Idaho" },
  { value: "IL", label: "Illinois" },
  { value: "IN", label: "Indiana" },
  { value: "IA", label: "Iowa" },
  { value: "KS", label: "Kansas" },
  { value: "KY", label: "Kentucky" },
  { value: "LA", label: "Louisiana" },
  { value: "ME", label: "Maine" },
  { value: "MD", label: "Maryland" },
  { value: "MA", label: "Massachusetts" },
  { value: "MI", label: "Michigan" },
  { value: "MN", label: "Minnesota" },
  { value: "MS", label: "Mississippi" },
  { value: "MO", label: "Missouri" },
  { value: "MT", label: "Montana" },
  { value: "NE", label: "Nebraska" },
  { value: "NV", label: "Nevada" },
  { value: "NH", label: "New Hampshire" },
  { value: "NJ", label: "New Jersey" },
  { value: "NM", label: "New Mexico" },
  { value: "NY", label: "New York" },
  { value: "NC", label: "North Carolina" },
  { value: "ND", label: "North Dakota" },
  { value: "OH", label: "Ohio" },
  { value: "OK", label: "Oklahoma" },
  { value: "OR", label: "Oregon" },
  { value: "PA", label: "Pennsylvania" },
  { value: "RI", label: "Rhode Island" },
  { value: "SC", label: "South Carolina" },
  { value: "SD", label: "South Dakota" },
  { value: "TN", label: "Tennessee" },
  { value: "TX", label: "Texas" },
  { value: "UT", label: "Utah" },
  { value: "VT", label: "Vermont" },
  { value: "VA", label: "Virginia" },
  { value: "WA", label: "Washington" },
  { value: "WV", label: "West Virginia" },
  { value: "WI", label: "Wisconsin" },
  { value: "WY", label: "Wyoming" },
];

// ---------------------------------------------------------------------------
// Step 1: Household Profile
// ---------------------------------------------------------------------------

export function StepProfile() {
  const data = useWizardStore((s) => s.data);
  const setField = useWizardStore((s) => s.setField);
  const { showErrors, errors } = useContext(WizardErrorContext);

  const isJoint = data.household.filing_status === "joint";
  const endYear = projectionEndYear(householdHorizon(data));

  return (
    <div>
      <StepHeader
        title="Household Profile"
        description="Tell us about your household filing status and birth dates."
      />

      <div className="flex flex-col gap-4">
        {/* Nickname */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel htmlFor="field-nickname" tip="e.g. 'Retire at 65' — shown on your dashboard.">
            Plan nickname <span className="text-muted-foreground font-normal">(optional)</span>
          </FieldLabel>
          <Input
            id="field-nickname"
            type="text"
            placeholder="e.g. Retire at 65"
            value={data.household.nickname ?? ""}
            onChange={(e) => setField("household.nickname", e.target.value)}
          />
        </div>

        {/* Filing Status — segmented toggle group */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="filing-status"
            tip="Determines your tax brackets, standard deduction, and IRMAA thresholds."
          >
            Filing Status
          </FieldLabel>
          <ToggleGroup
            type="single"
            id="filing-status"
            value={data.household.filing_status}
            onValueChange={(val) => {
              if (val) setField("household.filing_status", val);
            }}
          >
            <ToggleGroupItem value="single">Single</ToggleGroupItem>
            <ToggleGroupItem value="joint">Married Filing Jointly</ToggleGroupItem>
          </ToggleGroup>
          {showErrors && errors["filing_status"] && (
            <FieldError message={errors["filing_status"]} />
          )}
        </div>

        {/* Your Birth Date */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="self-birth-date"
            tip="Used to calculate your current age, RMD start age, and Social Security benefit timing."
          >
            Your Birth Date
          </FieldLabel>
          {/* No redundant aria-label — association is via htmlFor on the Label above */}
          <Input
            id="self-birth-date"
            type="date"
            value={data.household.self_birth_date}
            onChange={(e) =>
              setField("household.self_birth_date", e.target.value)
            }
            className={cn(
              showErrors && errors["self_birth_date"] && "border-destructive"
            )}
          />
          {showErrors && errors["self_birth_date"] && (
            <FieldError message={errors["self_birth_date"]} />
          )}
        </div>

        {/* Spouse Birth Date — only when joint */}
        {isJoint && (
          <div className="flex flex-col gap-1.5">
            <FieldLabel
              htmlFor="spouse-birth-date"
              tip="Both birth dates matter: RMDs and Social Security benefits are calculated per person."
            >
              Spouse Birth Date
            </FieldLabel>
            {/* No redundant aria-label — association is via htmlFor on the Label above */}
            <Input
              id="spouse-birth-date"
              type="date"
              value={data.household.spouse_birth_date ?? ""}
              onChange={(e) =>
                setField("household.spouse_birth_date", e.target.value)
              }
              className={cn(
                showErrors &&
                  errors["spouse_birth_date"] &&
                  "border-destructive"
              )}
            />
            {showErrors && errors["spouse_birth_date"] && (
              <FieldError message={errors["spouse_birth_date"]} />
            )}
          </div>
        )}

        {/* Planning horizon: explicit ages, starting at a visible default */}
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <FieldLabel htmlFor="self-death-age">Plan through age (you)</FieldLabel>
            <Input
              id="self-death-age"
              type="number"
              min={40}
              max={120}
              value={data.household.self_death_age ?? ""}
              onChange={(e) =>
                setField(
                  "household.self_death_age",
                  e.target.value === "" ? null : Number(e.target.value)
                )
              }
              className={cn(showErrors && errors["self_death_age"] && "border-destructive")}
            />
            {showErrors && errors["self_death_age"] && (
              <FieldError message={errors["self_death_age"]} />
            )}
          </div>
          {isJoint && (
            <div className="flex flex-col gap-1.5">
              <FieldLabel
                htmlFor="spouse-death-age"
                tip="The projection continues through whichever of you reaches their age later. A longer horizon tests whether the money lasts longer."
              >
                Plan through age (spouse)
              </FieldLabel>
              <Input
                id="spouse-death-age"
                type="number"
                min={40}
                max={120}
                value={data.household.spouse_death_age ?? ""}
                onChange={(e) =>
                  setField(
                    "household.spouse_death_age",
                    e.target.value === "" ? null : Number(e.target.value)
                  )
                }
                className={cn(showErrors && errors["spouse_death_age"] && "border-destructive")}
              />
              {showErrors && errors["spouse_death_age"] && (
                <FieldError message={errors["spouse_death_age"]} />
              )}
            </div>
          )}
          <p className="col-span-2 text-xs text-muted-foreground" data-testid="plan-through-help">
            We&apos;ll project your finances through this age. This is a planning assumption,
            not a prediction of lifespan. A new plan starts at {DEFAULT_PLAN_THROUGH_AGE}, a
            modeling default; change it to suit your plan.
            {endYear != null && <> The projection runs through {endYear}.</>}
          </p>
        </div>

        {/* State of Residence */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="state"
            tip="Determines your state income tax. No-income-tax states and the state treatment of Social Security are applied; exemptions for pension or IRA income are not modelled."
          >
            State of Residence
          </FieldLabel>
          <Select
            value={data.household.state}
            onValueChange={(val) => setField("household.state", val)}
          >
            <SelectTrigger id="state">
              <SelectValue placeholder="Select state" />
            </SelectTrigger>
            <SelectContent>
              {US_STATES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {showErrors && errors["state"] && (
            <FieldError message={errors["state"]} />
          )}
        </div>
      </div>
    </div>
  );
}
