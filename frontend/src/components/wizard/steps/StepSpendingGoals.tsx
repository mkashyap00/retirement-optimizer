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
import { CurrencyInput } from "@/components/ui/currency-input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { WizardErrorContext } from "../WizardContext";
import { BRACKET_CAP_OPTIONS, bracketCapSelectValue } from "@/lib/brackets";
import { FieldLabel, FieldError, StepHeader } from "./shared";

// ---------------------------------------------------------------------------
// Step 5: Spending and goals
// ---------------------------------------------------------------------------

export function StepSpendingGoals() {
  const data = useWizardStore((s) => s.data);
  const setField = useWizardStore((s) => s.setField);
  const { showErrors, errors } = useContext(WizardErrorContext);

  return (
    <div>
      <StepHeader
        title="Spending and goals"
        description="What you would like to spend, how spending responds to markets, and any goals or limits."
      />

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="required-spending">How much would you like to spend each year?</Label>
          <p className="text-xs text-muted-foreground" id="required-spending-help">
            Household spending in today&apos;s dollars, excluding income taxes. Enter the full
            amount before subtracting Social Security or other income. The model calculates
            income taxes separately.
          </p>
          <CurrencyInput
            id="required-spending"
            aria-describedby="required-spending-help"
            value={data.settings.required_spending}
            onChange={(n) => setField("settings.required_spending", n ?? 0)}
          />
          {showErrors && errors["required_spending"] && (
            <FieldError message={errors["required_spending"]} />
          )}
        </div>

        {/* Spending rule — fixed vs guardrails */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel
            htmlFor="spending-rule"
            tip="Keep spending the same: spend the amount above every year regardless of markets — the strict test of whether the plan lasts. Cut back, then recover: cut spending about 10% when your withdrawal rate drifts 20% above where it started, and restore it when markets recover, never going below your minimum. A cut is a real loss, so the optimizer counts spending given up above the minimum at half weight rather than treating it as free safety."
          >
            If markets go badly
          </FieldLabel>
          <ToggleGroup
            type="single"
            id="spending-rule"
            value={data.settings.spending_rule ?? "fixed"}
            onValueChange={(val) => {
              if (val) setField("settings.spending_rule", val);
            }}
            className="flex-wrap"
          >
            <ToggleGroupItem value="fixed">
              Keep spending the same (default)
            </ToggleGroupItem>
            <ToggleGroupItem value="guardrails">
              Cut back, then recover
            </ToggleGroupItem>
          </ToggleGroup>
        </div>

        {/* Minimum — only meaningful once spending can flex */}
        {data.settings.spending_rule === "guardrails" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="spending-floor">
              Minimum annual spending{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <p className="text-xs text-muted-foreground" id="spending-floor-help">
              Planned spending cuts will not go below this amount. Leave it blank for no
              minimum: cuts can continue while markets stay poor, and every dollar cut is
              counted as a full loss.
            </p>
            <CurrencyInput
              id="spending-floor"
              aria-describedby="spending-floor-help"
              value={data.settings.spending_floor ?? undefined}
              onChange={(n) => setField("settings.spending_floor", n)}
            />
            {showErrors && errors["spending_floor"] && (
              <FieldError message={errors["spending_floor"]} />
            )}
          </div>
        )}

        <section className="rounded-lg border border-border px-4 py-3" data-testid="advanced-limits">
          <h3 className="text-sm font-medium text-foreground">Optional goals and limits</h3>
          <div className="mt-4 flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <FieldLabel
                htmlFor="target-estate"
                tip="Optional bequest goal, in the dollars of the plan's final year. It does not change the winning strategy; a scenario counts as a success only if it also ends with at least this heir-adjusted estate."
              >
                Target Estate{" "}
                <span className="text-muted-foreground font-normal">(optional)</span>
              </FieldLabel>
              <CurrencyInput
                id="target-estate"
                value={data.constraints.target_estate}
                onChange={(n) => setField("constraints.target_estate", n)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <FieldLabel
                htmlFor="max-conversion"
                tip="Optional cap on annual Roth conversion. Useful to spread conversions over more years or stay below a bracket ceiling."
              >
                Max Roth Conversion / Year{" "}
                <span className="text-muted-foreground font-normal">(optional)</span>
              </FieldLabel>
              <CurrencyInput
                id="max-conversion"
                value={data.constraints.max_conversion_per_year}
                onChange={(n) => setField("constraints.max_conversion_per_year", n)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <FieldLabel
                htmlFor="marginal-rate-limit"
                tip="Optional ceiling on the ORDINARY-INCOME bracket a conversion may reach. e.g. 22% means no conversion that would push your ordinary income past the top of the 22% bracket in any year. Note this caps the bracket, not what the conversion actually costs you: a dollar converted inside the 12% bracket can still cost 25-30% once it drags more Social Security into taxability or crosses an IRMAA tier. The optimizer prices those effects correctly when ranking plans — this cap just bounds the bracket."
              >
                Max ordinary-income bracket{" "}
                <span className="text-muted-foreground font-normal">(optional)</span>
              </FieldLabel>
              <Select
                value={bracketCapSelectValue(data.constraints.marginal_rate_limit)}
                onValueChange={(v) =>
                  setField("constraints.marginal_rate_limit", v === "none" ? undefined : Number(v))
                }
              >
                <SelectTrigger id="marginal-rate-limit">
                  <SelectValue placeholder="No limit" />
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
          </div>
        </section>
      </div>
    </div>
  );
}
