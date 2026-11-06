"use client";

import type { YearRationale } from "@/lib/types";
import { formatPercent } from "@/lib/utils";

interface RationalePanelProps {
  rationale: YearRationale;
}

export function RationalePanel({ rationale }: RationalePanelProps) {
  const { narrative, warnings, conversion } = rationale;

  return (
    <div className="space-y-3 px-4 py-3 bg-muted/30 rounded-md text-sm">
      {/* Narrative */}
      <p className="text-foreground leading-relaxed">{narrative}</p>

      {/* Warning badges */}
      {warnings.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {warnings.map((w, i) => {
            const crossed = w.distance < 0;
            return (
              <span
                key={i}
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border ${
                  crossed
                    ? "bg-red-100 text-red-800 border-red-200"
                    : "bg-amber-100 text-amber-800 border-amber-200"
                }`}
                data-testid={crossed ? "warning-red" : "warning-amber"}
              >
                {w.consequence}
              </span>
            );
          })}
        </div>
      )}

      {/* All-in cost of the conversion.  This is the honest answer to "what did
          converting actually cost me": total extra tax vs. not converting,
          divided by the amount converted.  It routinely exceeds the bracket the
          conversion nominally sits in, because it also carries the state tax,
          any IRMAA surcharge, and the extra Social Security dragged into
          taxable income.  Despite the field name it is an AVERAGE per converted
          dollar, not the rate on the last dollar — so it is not labelled
          "marginal" here. */}
      {conversion && (
        <div className="text-muted-foreground text-xs border-t pt-2">
          <span className="font-medium">Cost of this conversion:</span>{" "}
          <span
            className="font-medium text-foreground"
            data-testid="conversion-cost-rate"
          >
            {formatPercent(conversion.marginal_cost_rate * 100)}
          </span>{" "}
          per dollar converted — the extra tax it causes (federal, state, IRMAA,
          and added Social Security taxation) versus not converting this year.
        </div>
      )}

      {/* BETR line when conversion is present. Reported as a neutral
          single-year break-even figure, not a favorable/unfavorable verdict —
          the per-year break-even routinely disagrees with the winning
          strategy, which is chosen on lifetime totals. */}
      {conversion && (
        <div className="text-muted-foreground text-xs border-t pt-2">
          <span className="font-medium">BETR:</span>{" "}
          single-year break-even{" "}
          <span className="font-medium text-foreground">
            {formatPercent(conversion.betr * 100)}
          </span>{" "}
          vs. projected future{" "}
          <span className="font-medium text-foreground">
            {formatPercent(conversion.projected_future_marginal_rate * 100)}
          </span>
          . Prices one year alone; the winning strategy is chosen on lifetime
          totals.
        </div>
      )}
    </div>
  );
}
