"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
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

interface TaxChartProps {
  rows: YearRow[];
  milestones?: Milestone[];
}

export function TaxChart({ rows, milestones }: TaxChartProps) {
  const data = rows.map((r) => ({
    year: r.year,
    Federal: r.federal_tax,
    State: r.state_tax,
    IRMAA: r.irmaa,
  }));

  return (
    <ChartFrame title="Annual taxes by type">
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
          <Tooltip formatter={(value: number) => formatCurrency(value)} {...TOOLTIP_STYLE} />
          <Legend />
          {milestoneLines(milestones)}
          <Bar dataKey="Federal" stackId="tax" fill={SERIES.emerald} />
          <Bar dataKey="State" stackId="tax" fill={SERIES.gold} />
          <Bar dataKey="IRMAA" stackId="tax" fill={SERIES.clay} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
