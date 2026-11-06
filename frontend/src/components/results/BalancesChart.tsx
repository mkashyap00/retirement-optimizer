"use client";

import {
  AreaChart,
  Area,
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
  FILL,
  GRID_STROKE,
  AXIS_TICK,
  AXIS_LINE,
  TOOLTIP_STYLE,
} from "./chartTheme";

interface BalancesChartProps {
  rows: YearRow[];
  milestones?: Milestone[];
}

export function BalancesChart({ rows, milestones }: BalancesChartProps) {
  const data = rows.map((r) => ({
    year: r.year,
    Taxable: r.balance_taxable,
    Traditional: r.balance_traditional,
    Roth: r.balance_roth,
  }));

  return (
    <ChartFrame title="Account balances by year">
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis dataKey="year" tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={AXIS_LINE} />
          <YAxis
            tickFormatter={(v) => `$${(v / 1_000_000).toFixed(1)}M`}
            tick={AXIS_TICK}
            axisLine={AXIS_LINE}
            tickLine={AXIS_LINE}
          />
          <Tooltip formatter={(value: number) => formatCurrency(value)} {...TOOLTIP_STYLE} />
          <Legend />
          {milestoneLines(milestones)}
          <Area
            type="monotone"
            dataKey="Taxable"
            stackId="1"
            stroke={SERIES.gold}
            fill={FILL.gold}
          />
          <Area
            type="monotone"
            dataKey="Traditional"
            stackId="1"
            stroke={SERIES.emerald}
            fill={FILL.emerald}
          />
          <Area
            type="monotone"
            dataKey="Roth"
            stackId="1"
            stroke={SERIES.teal}
            fill={FILL.teal}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
