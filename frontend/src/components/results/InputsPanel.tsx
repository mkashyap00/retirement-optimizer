"use client";

import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { HouseholdDetail, TaxTables } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { capitalGainsLines } from "@/lib/capitalGains";
import {
  ACCOUNT_LABELS,
  FILING_LABELS,
  IRMAA_LABELS,
  OWNER_LABELS,
  yearSpan,
} from "@/lib/labels";

interface InputsPanelProps {
  inputs: HouseholdDetail;
  /** The run's objective id. Absent on runs saved before October 2026, which
   *  were scored under the retired taxes-vs-estate priority. */
  objective?: string | null;
  /** The run's tax-table provenance; absent on older runs. */
  taxTables?: TaxTables | null;
  /** How the run treated claim ages, so the entered age is not mistaken for
   *  the searched or recommended one. Absent: the entered ages are shown. */
  claims?: ClaimContext;
}

export interface ClaimContext {
  /** A joint claim-age search. */
  joint: boolean;
  /** Joint runs: which people's ages were searched (the rest held fixed). */
  searched?: { self?: boolean; spouse?: boolean };
  /** The ages the result uses: recommended (joint) or run at (fixed). */
  used?: { self?: number | null; spouse?: number | null };
}

/** "Entered 67 · searched · recommended 69", "Already receiving (claimed at
 *  63)", or "67 (entered)". */
export function claimAgeText(
  person: "self" | "spouse",
  settings: HouseholdDetail["settings"],
  claims?: ClaimContext,
): string {
  const entered = person === "self" ? settings.ss_claim_age_self : settings.ss_claim_age_spouse;
  const receiving = person === "self" ? settings.ss_receiving_self : settings.ss_receiving_spouse;
  if (receiving) return `Already receiving (claimed at ${entered})`;
  const used = claims?.used?.[person];
  if (claims?.joint) {
    if (claims.searched?.[person]) {
      return `${entered != null ? `Entered ${entered}` : "No comparison age"} · searched · ` +
        `recommended ${used ?? "—"}`;
    }
    return `Held fixed at ${used ?? entered}`;
  }
  if (used != null && used !== entered) return `Entered ${entered ?? "—"} · this run used ${used}`;
  return `${entered ?? "—"} (entered)`;
}

const CATEGORY_LABELS: Record<string, string> = {
  salary: "Salary",
  pension: "Pension",
  rental: "Rental",
  interest: "Interest",
  qualified_dividend: "Qualified dividends",
  nonqualified_dividend: "Non-qualified dividends",
};

/** Same wording as the exports (backend reports/assumption_labels.py). */
export const OBJECTIVE_LABEL =
  "After-tax estate, less unfunded spending (taxes reported, not scored)";

/** Labels for runs scored under the retired taxes-vs-estate priority. */
const PRIORITY_LABELS: Record<string, string> = {
  "1": "Estate",
  "0.5": "Balanced",
  "0": "Lifetime taxes",
};

const WINDOW_LABELS: Record<string, string> = {
  anytime: "Anytime",
  pre_medicare: "Pre-Medicare",
  pre_rmd: "Pre-RMD",
  pre_ss: "Pre-Social Security",
};

/** The COLA a run used. Snapshots saved before the setting existed have no
 *  ss_cola key at all, and those runs held benefits flat. */
function colaLabel(settings: HouseholdDetail["settings"]): string {
  if (!("ss_cola" in settings)) return "None (benefits held flat)";
  if (settings.ss_cola == null) {
    return `Follows inflation (${formatPercent(Math.max(0, settings.inflation) * 100)})`;
  }
  return settings.ss_cola === 0
    ? "None (benefits held flat)"
    : formatPercent(settings.ss_cola * 100);
}

/** Same wording as the exports (backend reports/assumption_labels.py). */
export function taxTablesLabel(tt: TaxTables | null | undefined): string {
  if (!tt) return "Frozen at the last published year";
  const states = tt.state_indexed.length ? tt.state_indexed.join(", ") : "none";
  return (
    `Federal and IRMAA published through ${tt.federal_published_through}, ` +
    `state through ${tt.state_published_through}; later years indexed at ` +
    `${(tt.indexation_rate * 100).toFixed(1)}% (state: ${states} only; ` +
    `IRMAA premiums not projected)`
  );
}

function Item({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-0.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium text-right tabular-nums">{value}</dd>
    </div>
  );
}

/** A long value on its own line under its label. */
function WideItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="py-0.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="font-display text-sm font-semibold text-primary mb-1.5">
        {title}
      </h4>
      <dl className="text-sm space-y-0">{children}</dl>
    </div>
  );
}

/**
 * Collapsible summary of the exact inputs that produced a run
 * (from the run's stored snapshot — not the household's current state).
 */
export function InputsPanel({ inputs, objective, taxTables, claims }: InputsPanelProps) {
  const [open, setOpen] = useState(false);
  const { household, accounts, income, settings, constraints } = inputs;
  const gains = capitalGainsLines(inputs.capital_gains);

  return (
    <div className="rounded-xl border border-border bg-card shadow-folio overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-muted/30 transition-colors"
        data-testid="inputs-panel-toggle"
      >
        <span className="flex items-center gap-2 font-display text-lg font-semibold text-primary">
          <span className="inline-block w-1 h-5 rounded-full bg-accent" aria-hidden="true" />
          Inputs used for this run
        </span>
        <ChevronDown
          className={`w-5 h-5 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="px-6 pb-6 space-y-6" data-testid="inputs-panel-body">
          <div className="grid gap-x-10 gap-y-6 md:grid-cols-2">
          <Section title="Household">
            <Item label="Filing status" value={FILING_LABELS[household.filing_status] ?? household.filing_status} />
            <Item label="Your birth date" value={household.self_birth_date} />
            {household.spouse_birth_date && (
              <Item label="Spouse birth date" value={household.spouse_birth_date} />
            )}
            <Item label="State" value={household.state} />
            {household.self_death_age != null && (
              <Item label="Plan to age (you)" value={household.self_death_age} />
            )}
            {household.spouse_death_age != null && (
              <Item label="Plan to age (spouse)" value={household.spouse_death_age} />
            )}
          </Section>

          <Section title="Accounts">
            {accounts.length === 0 && <p className="text-sm text-muted-foreground">None</p>}
            {accounts.map((a, i) => (
              <React.Fragment key={i}>
                <Item
                  label={`${ACCOUNT_LABELS[a.account_type] ?? a.account_type} (${OWNER_LABELS[a.owner] ?? a.owner})`}
                  value={formatCurrency(a.balance)}
                />
                {a.basis != null && a.account_type !== "roth" && (
                  <Item
                    label={a.account_type === "traditional" ? "  After-tax basis" : "  Cost basis"}
                    value={formatCurrency(a.basis)}
                  />
                )}
                {a.roth_opened_year != null && (
                  <Item
                    label={`  Roth opened`}
                    value={a.roth_opened_year}
                  />
                )}
              </React.Fragment>
            ))}
          </Section>

          <Section title="Income">
            {income.length === 0 && (
              <p className="text-sm text-muted-foreground">None</p>
            )}
            {income.map((inc, i) => {
              const span = yearSpan(inc.start_year, inc.end_year);
              return (
                <Item
                  key={i}
                  label={`${CATEGORY_LABELS[inc.category] ?? inc.category} (${OWNER_LABELS[inc.owner] ?? inc.owner})`}
                  value={`${formatCurrency(inc.amount)}/yr${span ? ` · ${span}` : ""}`}
                />
              );
            })}
            {gains.map(([label, value]) => <Item key={label} label={label} value={value} />)}
          </Section>

          <Section title="Social Security">
            {settings.ss_pia_self == null && settings.ss_pia_spouse == null && (
              <p className="text-sm text-muted-foreground">None</p>
            )}
            {(["self", "spouse"] as const).map((person) => {
              const pia = person === "self" ? settings.ss_pia_self : settings.ss_pia_spouse;
              if (pia == null) return null;
              const who = person === "self" ? "you" : "spouse";
              return (
                <React.Fragment key={person}>
                  {/* A PIA is the benefit at full retirement age, not the
                      payment at the claim age the plan uses. */}
                  <Item
                    label={`Benefit at full retirement age (${who})`}
                    value={`${formatCurrency(pia)}/mo`}
                  />
                  <Item label={`Claim age (${who})`} value={claimAgeText(person, settings, claims)} />
                </React.Fragment>
              );
            })}
          </Section>
          <Section title="Assumptions">
            <Item
              label="Annual spending"
              value={formatCurrency(settings.required_spending)}
            />
            <Item label="Inflation" value={formatPercent(settings.inflation * 100)} />
            <Item label="Social Security COLA" value={colaLabel(settings)} />
            <Item
              label="Nominal return"
              value={formatPercent(settings.nominal_return * 100)}
            />
            {!objective && (
              <Item
                label="Optimization priority"
                value={
                  PRIORITY_LABELS[String(settings.estate_weight ?? 1)] ??
                  `Estate weight ${settings.estate_weight}`
                }
              />
            )}
            <Item
              label="If markets go badly"
              value={
                settings.spending_rule === "guardrails"
                  ? "Cut back, then recover"
                  : "Keep spending the same"
              }
            />
            {settings.spending_floor != null && (
              <Item
                label="Essential spending floor"
                value={formatCurrency(Number(settings.spending_floor))}
              />
            )}
            {constraints.irmaa_policy && (
              <Item label="IRMAA policy" value={IRMAA_LABELS[constraints.irmaa_policy] ?? constraints.irmaa_policy} />
            )}
            {constraints.conversion_window && (
              <Item
                label="Conversion window"
                value={WINDOW_LABELS[constraints.conversion_window] ?? constraints.conversion_window}
              />
            )}
            {/* Decimals arrive from the API as strings — coerce before math. */}
            <Item
              label="Max ordinary-income bracket"
              value={
                constraints.marginal_rate_limit != null
                  ? `${Math.round(Number(constraints.marginal_rate_limit) * 100)}% bracket`
                  : "No limit"
              }
            />
            <Item
              label="Max conversion / yr"
              value={
                constraints.max_conversion_per_year != null
                  ? formatCurrency(Number(constraints.max_conversion_per_year))
                  : "No limit"
              }
            />
            {constraints.preserve_taxable != null && (
              <Item
                label="Preserve taxable"
                value={constraints.preserve_taxable ? "Yes" : "No"}
              />
            )}
          </Section>
          </div>

          {/* Long values get the full width. */}
          <Section title="Method">
            <WideItem label="Tax tables" value={taxTablesLabel(taxTables)} />
            {objective && <WideItem label="Objective" value={OBJECTIVE_LABEL} />}
          </Section>
        </div>
      )}
    </div>
  );
}
