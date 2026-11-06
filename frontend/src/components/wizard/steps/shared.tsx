"use client";

import React, { useState } from "react";
import { HelpCircle, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Tooltip } from "@/components/ui/tooltip";
import type { HouseholdPayload } from "@/lib/types";

// ---------------------------------------------------------------------------
// Shared field primitives
// ---------------------------------------------------------------------------

/** Label with optional help tooltip (HelpCircle icon, keyboard-focusable). */
export function FieldLabel({
  htmlFor,
  children,
  tip,
}: {
  htmlFor: string;
  children: React.ReactNode;
  tip?: string;
}) {
  if (!tip) {
    return <Label htmlFor={htmlFor}>{children}</Label>;
  }
  return (
    <div className="flex items-center gap-1.5">
      <Label htmlFor={htmlFor}>{children}</Label>
      <InfoTip text={tip} />
    </div>
  );
}

/** The "?" button that shows a tooltip. */
export function InfoTip({ text }: { text: string }) {
  return (
    <Tooltip content={text} side="right">
      {/* aria-label intentionally omitted to avoid collisions with getByLabelText; sr-only text provides accessible name */}
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
        tabIndex={0}
      >
        <HelpCircle className="w-3.5 h-3.5" aria-hidden="true" />
        <span className="sr-only">More info</span>
      </button>
    </Tooltip>
  );
}

/** Inline validation error message. */
export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="text-xs text-destructive mt-0.5">{message}</p>;
}

// ---------------------------------------------------------------------------
// Section header within a step
// ---------------------------------------------------------------------------

export function StepHeader({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="mb-5">
      <h2 className="text-lg font-semibold font-display text-foreground leading-tight">
        {title}
      </h2>
      <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collapsible list entries (accounts, income)
// ---------------------------------------------------------------------------

/** Which entries of a list are collapsed to a one-line summary. Entries
 *  already complete when the step opens start collapsed; any other entry
 *  collapses only when the user says Done -- never while it is being typed
 *  into. Removing an entry shifts the indexes after it. */
export function useCollapsed(initiallyComplete: () => number[]) {
  const [collapsed, setCollapsed] = useState<Set<number>>(() => new Set(initiallyComplete()));
  return {
    isCollapsed: (i: number) => collapsed.has(i),
    collapse: (i: number) => setCollapsed((c) => new Set(c).add(i)),
    expand: (i: number) =>
      setCollapsed((c) => {
        const n = new Set(c);
        n.delete(i);
        return n;
      }),
    removed: (i: number) =>
      setCollapsed((c) => new Set(Array.from(c).filter((x) => x !== i).map((x) => (x > i ? x - 1 : x)))),
  };
}

export function money(n: number | null | undefined): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n ?? 0);
}

export function EntrySummary({
  text,
  what,
  onEdit,
  onRemove,
  testId,
}: {
  text: string;
  what: string;
  onEdit: () => void;
  onRemove: () => void;
  testId: string;
}) {
  return (
    <div
      className="rounded-lg border border-border bg-card px-4 py-2.5 shadow-folio flex items-center justify-between gap-3"
      data-testid={testId}
    >
      <span className="text-sm">{text}</span>
      <span className="flex gap-1 flex-shrink-0">
        <Button variant="ghost" size="sm" onClick={onEdit} aria-label={`Edit ${what}`}>
          Edit
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRemove}
          aria-label={`Remove ${what}`}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
        </Button>
      </span>
    </div>
  );
}

/** The preview request for the wizard's current answers, or null while the
 *  birth dates it needs are missing. */
export function claimPreviewBody(data: HouseholdPayload) {
  const hh = data.household;
  if (!hh.self_birth_date || (hh.filing_status === "joint" && !hh.spouse_birth_date)) return null;
  const joint = hh.filing_status === "joint";
  return {
    household: {
      filing_status: hh.filing_status,
      state: hh.state,
      self_birth_date: hh.self_birth_date,
      ...(joint ? { spouse_birth_date: hh.spouse_birth_date } : {}),
    },
    income: data.income.filter((i) => i.amount > 0),
    ss_pia_self: data.settings.ss_pia_self ?? null,
    ss_claim_age_self: data.settings.ss_claim_age_self ?? null,
    ss_receiving_self: data.settings.ss_receiving_self ?? null,
    ...(joint
      ? {
          ss_pia_spouse: data.settings.ss_pia_spouse ?? null,
          ss_claim_age_spouse: data.settings.ss_claim_age_spouse ?? null,
          ss_receiving_spouse: data.settings.ss_receiving_spouse ?? null,
        }
      : {}),
  } as Parameters<typeof import("@/lib/api").previewClaimAges>[0];
}
