"use client";

import React from "react";
import { ReferenceLine } from "recharts";
import type { Milestone } from "@/lib/milestones";
import { MILESTONE_STROKE } from "./chartTheme";
import { STEADY_LABEL } from "@/lib/marketModel";

/** A chart card whose title says which projection it shows. */
export function ChartFrame({ title, children, testId }: {
  title: string;
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-folio" data-testid={testId}>
      <h3 className="font-display text-base font-semibold text-primary">{title}</h3>
      <p className="mb-4 text-xs text-muted-foreground">{STEADY_LABEL}</p>
      {children}
    </div>
  );
}

/** Dashed vertical markers; the years are named in MilestoneList. Recharts
 *  needs these as direct children of the chart, so this returns an array. */
export function milestoneLines(milestones: Milestone[] = []) {
  return milestones.map((m) => (
    <ReferenceLine key={m.year} x={m.year} stroke={MILESTONE_STROKE} strokeDasharray="4 3" />
  ));
}

/** The milestones in words, shown once beside the charts -- the markers are
 *  not the only place they appear. */
export function MilestoneList({ milestones }: { milestones: Milestone[] }) {
  if (milestones.length === 0) return null;
  return (
    <p className="text-sm text-muted-foreground" data-testid="chart-milestones">
      <span className="font-medium text-foreground">Dashed lines mark: </span>
      {milestones.map((m, i) => (
        <span key={m.year}>
          {i > 0 && " · "}
          {m.year} {m.label}
        </span>
      ))}
    </p>
  );
}
