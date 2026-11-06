"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LabelList,
} from "recharts";
import type { YearRow } from "@/lib/types";
import type { Milestone } from "@/lib/milestones";
import { ChartFrame, milestoneLines } from "./ChartFrame";
import { formatCurrency } from "@/lib/utils";
import {
  SERIES,
  GRID_STROKE,
  AXIS_TICK,
  AXIS_LINE,
  TOOLTIP_STYLE,
} from "./chartTheme";

interface ConversionChartProps {
  rows: YearRow[];
  milestones?: Milestone[];
}

export function ConversionChart({ rows, milestones }: ConversionChartProps) {
  const data = rows
    .filter((r) => r.conversion > 0)
    .map((r) => ({
      year: r.year,
      Conversion: r.conversion,
      label:
        r.rationale?.conversion?.target_description ??
        `${r.year} conversion`,
    }));

  // No conversions: one line, not an empty chart.
  if (data.length === 0) {
    return (
      <p
        className="rounded-xl border border-border bg-card px-5 py-3 text-sm text-muted-foreground shadow-folio"
        data-testid="no-conversions-note"
      >
        <span className="font-medium text-foreground">Roth conversions:</span> none in this plan,
        so there is no conversion chart.
      </p>
    );
  }

  return (
    <ChartFrame title="Roth conversions by year">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis dataKey="year" tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={AXIS_LINE} />
          <YAxis
            tickFormatter={(v) => `$${(v / 1_000).toFixed(0)}k`}
            tick={AXIS_TICK}
            axisLine={AXIS_LINE}
            tickLine={AXIS_LINE}
          />
          <Tooltip
            formatter={(value: number) => [formatCurrency(value), "Conversion"]}
            {...TOOLTIP_STYLE}
          />
          {milestoneLines(milestones)}
          <Bar dataKey="Conversion" fill={SERIES.gold}>
            <LabelList
              dataKey="label"
              position="top"
              className="text-xs"
              formatter={(v: string) =>
                v.length > 18 ? v.slice(0, 18) + "…" : v
              }
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
