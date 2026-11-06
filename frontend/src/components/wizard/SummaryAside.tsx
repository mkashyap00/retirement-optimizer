"use client";

import React from "react";
import { useWizardStore } from "@/stores/wizardStore";
import { IRMAA_LABELS } from "@/lib/labels";

const FILING_LABELS: Record<string, string> = {
  single: "Single",
  joint: "Married Filing Jointly",
};


const WINDOW_LABELS: Record<string, string> = {
  anytime: "Anytime",
  pre_medicare: "Before Medicare (65)",
  pre_rmd: "Before RMDs (73, or 75 if born 1960+)",
  pre_ss: "Before Social Security",
};

function Dash() {
  return <span className="text-muted-foreground/50">—</span>;
}

function SectionMarker({ children }: { children: React.ReactNode }) {
  return (
    <dt className="col-span-2 pt-3 pb-0.5 text-xs font-semibold tracking-widest uppercase text-accent font-display first:pt-0">
      {children}
    </dt>
  );
}

function Row({
  label,
  value,
  "data-testid": testId,
}: {
  label: string;
  value: React.ReactNode;
  "data-testid"?: string;
}) {
  return (
    <>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xs font-medium text-right" data-testid={testId}>
        {value ?? <Dash />}
      </dd>
    </>
  );
}

function fmt(n: number | undefined): string {
  if (n == null) return "";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function pct(n: number | undefined): string {
  if (n == null) return "";
  return `${(n * 100).toFixed(1)}%`;
}

export function SummaryAside() {
  const data = useWizardStore((s) => s.data);

  const { household, settings, constraints, accounts, income } = data;
  const isJoint = household.filing_status === "joint";

  // Account totals by type
  const totals = { taxable: 0, traditional: 0, roth: 0 };
  for (const a of accounts) {
    if (a.account_type === "taxable") totals.taxable += a.balance ?? 0;
    else if (a.account_type === "traditional")
      totals.traditional += a.balance ?? 0;
    else if (a.account_type === "roth") totals.roth += a.balance ?? 0;
  }
  const totalBalance = accounts.reduce((s, a) => s + (a.balance ?? 0), 0);

  return (
    <aside
      aria-label="Your plan summary"
      className="rounded-lg border border-border bg-card shadow-folio p-4"
    >
      <h2 className="text-sm font-semibold font-display text-foreground mb-3">
        Your Plan
      </h2>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
        {/* ── Household ─────────────────────────────────────────────────── */}
        <SectionMarker>Household</SectionMarker>

        <Row
          label="Nickname"
          value={household.nickname || <Dash />}
          data-testid="aside-nickname"
        />
        <Row
          label="Filing"
          value={
            household.filing_status
              ? FILING_LABELS[household.filing_status]
              : undefined
          }
        />
        <Row label="State" value={household.state || undefined} />
        <Row
          label="Your DOB"
          value={household.self_birth_date || undefined}
        />
        {isJoint && (
          <Row
            label="Spouse DOB"
            value={household.spouse_birth_date || undefined}
          />
        )}

        {/* ── Assumptions ───────────────────────────────────────────────── */}
        <SectionMarker>Assumptions</SectionMarker>

        <Row
          label="Inflation"
          value={settings.inflation ? pct(settings.inflation) : undefined}
        />
        <Row
          label="Nominal return"
          value={settings.nominal_return ? pct(settings.nominal_return) : undefined}
        />
        <Row
          label="Medicare surcharge"
          value={
            constraints.irmaa_policy
              ? IRMAA_LABELS[constraints.irmaa_policy]
              : undefined
          }
        />
        <Row
          label="Conv. window"
          value={
            constraints.conversion_window
              ? WINDOW_LABELS[constraints.conversion_window]
              : undefined
          }
        />

        {/* ── Accounts ──────────────────────────────────────────────────── */}
        <SectionMarker>Accounts</SectionMarker>

        <Row
          label="Taxable"
          value={totals.taxable > 0 ? fmt(totals.taxable) : undefined}
        />
        <Row
          label="Traditional"
          value={totals.traditional > 0 ? fmt(totals.traditional) : undefined}
        />
        <Row
          label="Roth"
          value={totals.roth > 0 ? fmt(totals.roth) : undefined}
        />
        <Row
          label="Total"
          value={totalBalance > 0 ? fmt(totalBalance) : undefined}
        />

        {/* ── Income & SS ───────────────────────────────────────────────── */}
        <SectionMarker>Income &amp; SS</SectionMarker>

        <Row
          label="Income sources"
          value={income.length > 0 ? `${income.length}` : undefined}
        />
        <Row
          label="Your benefit at FRA"
          value={settings.ss_pia_self > 0 ? fmt(settings.ss_pia_self) : undefined}
        />
        {isJoint && settings.ss_pia_spouse != null && settings.ss_pia_spouse > 0 && (
          <Row label="Spouse benefit at FRA" value={fmt(settings.ss_pia_spouse)} />
        )}

        {/* ── Spending ──────────────────────────────────────────────────── */}
        <SectionMarker>Spending</SectionMarker>

        <Row
          label="Required/yr"
          value={
            settings.required_spending > 0
              ? fmt(settings.required_spending)
              : undefined
          }
        />
        {constraints.target_estate != null && constraints.target_estate > 0 && (
          <Row label="Target estate" value={fmt(constraints.target_estate)} />
        )}
      </dl>
    </aside>
  );
}
