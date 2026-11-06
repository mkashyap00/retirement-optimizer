"use client";

/**
 * Inline sale plan for one results year. Clicking "Plan this sale" fetches the
 * losses-first, cheapest-gain-first sell list for that year's taxable
 * withdrawal from the stored (app-level) portfolio and renders it in place —
 * no navigation.
 */

import { useState } from "react";
import Link from "next/link";
import { getSalePlan } from "@/lib/api";
import { isApiError } from "@/lib/apiError";
import type { SalePlanResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/utils";

interface Props {
  cash: number;
  spend: number;
  convTax: number;
}

function hpBadge(hp: string): string {
  if (hp === "long_term") return "LT";
  if (hp === "short_term") return "ST";
  return "?";
}

export function SalePlanInline({ cash, spend, convTax }: Props) {
  const [plan, setPlan] = useState<SalePlanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noPortfolio, setNoPortfolio] = useState(false);

  async function handlePlan() {
    setLoading(true);
    setError(null);
    setNoPortfolio(false);
    try {
      setPlan(await getSalePlan(cash));
    } catch (e) {
      if (isApiError(e, 404)) setNoPortfolio(true);
      else setError(e instanceof Error ? e.message : "Failed to plan this sale");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-2 space-y-2 text-xs">
      <div className="text-muted-foreground">
        {convTax > 0 ? (
          <>
            Of this year&apos;s {formatCurrency(cash)} taxable withdrawal:{" "}
            {formatCurrency(spend)} funds spending, {formatCurrency(convTax)}{" "}
            funds Roth conversion taxes.
          </>
        ) : (
          <>{formatCurrency(cash)} is withdrawn from the taxable account.</>
        )}
      </div>

      {!plan && (
        <Button
          size="sm"
          variant="default"
          onClick={handlePlan}
          disabled={loading}
        >
          {loading ? "Planning…" : "Plan this sale"}
        </Button>
      )}

      {noPortfolio && (
        <p className="text-muted-foreground">
          No holdings uploaded yet.{" "}
          <Link
            href="/portfolio"
            className="font-medium text-primary underline underline-offset-2"
          >
            Upload your portfolio
          </Link>{" "}
          on the Portfolio tab, then plan this sale.
        </p>
      )}
      {error && <p className="text-destructive">{error}</p>}

      {plan && (
        <div
          className="rounded-md border p-3 space-y-2"
          data-testid="inline-sale-plan"
        >
          <div className="text-muted-foreground">
            Sell to raise {formatCurrency(plan.cash_raised)} — prices as of
            today.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-muted-foreground border-b">
                  <th className="pb-1 pr-3">Ticker</th>
                  <th className="pb-1 pr-3">HP</th>
                  <th className="pb-1 pr-3 text-right">Shares</th>
                  <th className="pb-1 pr-3 text-right">Proceeds</th>
                  <th className="pb-1 text-right">Gain / Loss</th>
                </tr>
              </thead>
              <tbody>
                {plan.sold.map((s, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-1 pr-3 font-medium">{s.ticker}</td>
                    <td className="py-1 pr-3">{hpBadge(s.holding_period)}</td>
                    <td className="py-1 pr-3 text-right">
                      {s.shares_sold.toFixed(3)}
                    </td>
                    <td className="py-1 pr-3 text-right">
                      {formatCurrency(s.proceeds)}
                    </td>
                    <td
                      className={`py-1 text-right ${
                        s.realized_gain < 0 ? "text-green-700" : "text-red-700"
                      }`}
                    >
                      {formatCurrency(s.realized_gain)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {plan.warnings.length > 0 && (
            <ul className="text-amber-700 list-disc pl-4 space-y-1">
              {plan.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
