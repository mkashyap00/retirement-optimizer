/**
 * @jest-environment jsdom
 *
 * RTL tests for the results page components.
 */

import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";

import type { AlternativePolicy, OptimizationResult, YearRow, YearRationale } from "@/lib/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { MarketExplanation, SummaryCards } from "@/components/results/SummaryCards";
import { YearTable } from "@/components/results/YearTable";
import { strategyOptions, policyLabel, POLICY_LABELS } from "@/lib/policyLabels";
import { RationalePanel } from "@/components/results/RationalePanel";
import { AlternativesTable } from "@/components/results/AlternativesTable";
import { confidenceSentence, rankingRows } from "@/lib/resultSummary";

// ---------------------------------------------------------------------------
// Browser API polyfills for jsdom + recharts
// ---------------------------------------------------------------------------

beforeAll(() => {
  if (!global.ResizeObserver) {
    Object.defineProperty(global, "ResizeObserver", {
      writable: true,
      value: jest.fn().mockImplementation(() => ({
        observe: jest.fn(),
        unobserve: jest.fn(),
        disconnect: jest.fn(),
      })),
    });
  }

  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: jest.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
    });
  }
});

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

function makeRationale(overrides: Partial<YearRationale> = {}): YearRationale {
  return {
    year: 2026,
    age_self: 66,
    bracket: {
      bracket_rate: 0.22,
      bracket_top: 89075,
      headroom_used: 15000,
      headroom_remaining: 74075,
    },
    conversion: null,
    withdrawal: {
      order_used: ["traditional"],
      reason: "Spend from traditional first",
      rmd_amount: 0,
    },
    warnings: [],
    narrative: "No conversion this year; standard withdrawal from traditional.",
    ...overrides,
  };
}

function makeRow(year: number, overrides: Partial<YearRow> = {}): YearRow {
  return {
    year,
    age_self: 60 + year - 2020,
    conversion: 0,
    withdrawal_taxable: 0,
    withdrawal_traditional: 50000,
    withdrawal_roth: 0,
    rmd: 0,
    agi: 50000,
    magi: 50000,
    federal_tax: 5000,
    state_tax: 2000,
    irmaa: 0,
    total_tax: 7000,
    effective_rate: 0.14,
    marginal_rate: 0.22,
    net_spendable: 43000,
    required_spending: 40000,
    balance_taxable: 100000,
    balance_traditional: 800000,
    balance_roth: 50000,
    rationale: makeRationale({ year }),
    ...overrides,
  };
}

// Year with conversion + warning
const rowWithConversion = makeRow(2026, {
  conversion: 30000,
  rationale: makeRationale({
    year: 2026,
    narrative: "Converting $30,000 to fill the 22% bracket.",
    conversion: {
      action_id: "convert_30000",
      amount: 30000,
      target_description: "Fill 22% bracket",
      counterfactual_none_tax: 9000,
      marginal_cost_rate: 0.22,
      betr: 0.24,
      projected_future_marginal_rate: 0.28,
      betr_verdict: "favorable",
    },
    warnings: [
      {
        kind: "irmaa_tier",
        threshold: 194000,
        distance: -2000, // crossed!
        consequence: "IRMAA Tier 1 surcharge applies",
      },
    ],
  }),
});

const fixtureResult: OptimizationResult = {
  status: "ok",
  computation_time_seconds: 1.2,
  paths_evaluated: 500,
  monte_carlo_runs: 100,
  winning_policy: {
    policy_id: "policy_abc123",
    lifetime_taxes_nominal: 420000,
    lifetime_taxes_pv: 310000,
    terminal_estate: 1200000,
    success_probability: 0.92,
    score: 0.85,
    total_conversions: 90000,
    projected_future_marginal_rate: 0.28,
  },
  yearly_plan: [
    makeRow(2025),
    rowWithConversion,
    makeRow(2027),
  ],
  alternative_policies: [],
  warnings: ["Portfolio may be insufficient for a 30-year horizon"],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SummaryCards", () => {
  it("states what the score is made of when the run reports it", () => {
    const withComponents = {
      ...fixtureResult,
      winning_policy: {
        ...fixtureResult.winning_policy,
        score_components: {
          basis: "deterministic" as const,
          terminal_estate_pv: 900000,
          shortfall_pv: 50000,
          discretionary_shortfall_pv: 0,
          shortfall_weight: 1,
          discretionary_shortfall_weight: 0.5,
          deterministic_value: 850000,
          lifetime_taxes_pv: 310000,
        },
      },
    };
    render(<SummaryCards result={withComponents} />);
    const line = screen.getByTestId("score-components");
    expect(line).toHaveTextContent("after-tax estate $900,000");
    expect(line).toHaveTextContent("unfunded essential spending $50,000");
    expect(line).toHaveTextContent("= $850,000");
    expect(screen.getByTestId("card-estate")).toHaveTextContent("Equivalent to $900,000 today");
    expect(line).toHaveTextContent("not subtracted again");
  });

  it("omits the score line on runs saved before it was reported", () => {
    render(<SummaryCards result={fixtureResult} />);
    expect(screen.queryByTestId("score-components")).not.toBeInTheDocument();
  });

  it("renders formatted lifetime taxes", () => {
    render(<SummaryCards result={fixtureResult} />);
    // $420,000 formatted as currency
    expect(screen.getByText("$420,000")).toBeInTheDocument();
  });

  it("renders terminal estate", () => {
    render(<SummaryCards result={fixtureResult} />);
    expect(screen.getByText("$1,200,000")).toBeInTheDocument();
  });

  it("renders success probability rounded to whole points", () => {
    render(<SummaryCards result={fixtureResult} />);
    // Was "92.0%". The decimal implied a precision the simulation lacks --
    // the 95% interval is several points wide -- so it is rounded now.
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.queryByText("92.0%")).not.toBeInTheDocument();
  });

  it("shows the Monte Carlo interval beside the success probability", () => {
    render(<SummaryCards result={fixtureResult} />);
    // p=0.92, n=100 -> 1.96*sqrt(.92*.08/100) = 5.3pp -> "5 pts"
    const hint = screen
      .getAllByTestId("card-hint")
      .find((h) => h.textContent?.includes("scenarios"));
    expect(hint).toHaveTextContent("5 pts");
    expect(hint).toHaveTextContent("100 scenarios");
  });

  it("computes the interval from the policy's own scenario count", () => {
    // A policy can be scored on fewer scenarios than were requested; its
    // interval must use the count it actually rests on.
    const fewer = {
      ...fixtureResult,
      monte_carlo_runs: 300,
      winning_policy: { ...fixtureResult.winning_policy, monte_carlo_paths: 100 },
    };
    render(<SummaryCards result={fewer} />);
    const hint = screen
      .getAllByTestId("card-hint")
      .find((h) => h.textContent?.includes("scenarios"));
    expect(hint).toHaveTextContent("100 scenarios");
    expect(hint).toHaveTextContent("5 pts");
  });

  it("omits the interval when the run count is unknown", () => {
    const noRuns = { ...fixtureResult, monte_carlo_runs: 0 };
    render(<SummaryCards result={noRuns} />);
    for (const hint of screen.queryAllByTestId("card-hint")) {
      expect(hint).not.toHaveTextContent("scenarios");
    }
  });

  // The nominal card and the "Lifetime taxes (PV)" line below it showed two
  // different lifetime-tax figures with nothing tying them together. The card
  // now states the PV under the nominal figure, matching the line below.
  it("states lifetime taxes in today's dollars under the nominal figure", () => {
    const withRate = {
      ...fixtureResult,
      winning_policy: { ...fixtureResult.winning_policy, discount_rate: 0.03 },
    };
    render(<SummaryCards result={withRate} />);
    expect(
      screen.getByText("$310,000 in today's dollars (3% discount)")
    ).toBeInTheDocument();
  });

  it("falls back to the 2% default discount on runs that predate the field", () => {
    render(<SummaryCards result={fixtureResult} />);
    expect(
      screen.getByText("$310,000 in today's dollars (2% discount)")
    ).toBeInTheDocument();
  });

  it("states the conversion decision as a sentence", () => {
    render(<SummaryCards result={fixtureResult} />);
    expect(screen.getByTestId("recommendation-conversion")).toHaveTextContent(
      "$90,000 converted in total"
    );
  });

  // The winner used to sit in a muted strip BELOW the four cards, easy to
  // scroll past. It now leads the section as a banner.
  it("leads with the recommendation, above the measured figures", () => {
    render(<SummaryCards result={fixtureResult} />);
    const banner = screen.getByTestId("winning-policy-banner");
    // A fixed-age run says so.
    expect(banner).toHaveTextContent("Conversion optimization · recommended strategy");
    expect(banner).toHaveTextContent(/policy_abc123/);
    // Supporting detail, not part of the decision.
    expect(banner).not.toHaveTextContent(/marginal rate/i);
    const firstCard = screen.getByText("Spending funded in market scenarios");
    expect(
      banner.compareDocumentPosition(firstCard) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("labels every figure with what it measures", () => {
    render(
      <SummaryCards
        result={fixtureResult}
        market={{ scenarios: 100, meanReturn: 0.06, volatility: 0.12 }}
      />
    );
    expect(screen.getByText("Projected estate at a steady 6% annual return")).toBeInTheDocument();
    expect(screen.getByText("Lifetime taxes — steady-return projection")).toBeInTheDocument();
    const score = screen.getByTestId("card-score");
    expect(score).toHaveTextContent("Modeled score");
    expect(score).toHaveTextContent("Average after-tax estate minus spending-shortfall penalties.");
    expect(score).toHaveTextContent("Today's dollars · 100 market scenarios");
    expect(score).not.toHaveTextContent("ranks on");
    const estate = screen.getByTestId("card-estate");
    expect(estate).toHaveTextContent("At the end of your plan");
    // No today's-dollar breakdown stored: no equivalent claimed.
    expect(estate).not.toHaveTextContent("Equivalent to");
    expect(screen.getByTestId("score-explainer")).toHaveTextContent("28.0%");
  });

  it("does not call a forced policy the winner", () => {
    render(
      <SummaryCards result={{ ...fixtureResult, forced_policy: "policy_abc123" }} />
    );
    const banner = screen.getByTestId("winning-policy-banner");
    expect(banner).not.toHaveTextContent("Winning policy");
    expect(banner).toHaveTextContent("Strategy you chose to run");
  });

  it("shows winning policy id", () => {
    render(<SummaryCards result={fixtureResult} />);
    expect(screen.getByText(/policy_abc123/)).toBeInTheDocument();
  });

  // Years below target are not necessarily guardrail cuts: they include years
  // savings could not fund, with or without guardrails. The metric is worded
  // neutrally; guardrails are explained separately, and only when on.
  it("states years below target neutrally, and explains guardrails only when on", () => {
    const flexed = {
      ...fixtureResult,
      winning_policy: { ...fixtureResult.winning_policy, mean_years_reduced: 6.4 },
    };
    const { unmount } = render(<SummaryCards result={flexed} spendingRule="fixed" />);
    expect(screen.getByTestId("card-note")).toHaveTextContent(
      "Spending below target in approximately 6 years per market scenario.",
    );
    expect(screen.getByTestId("card-note")).not.toHaveTextContent(/guardrail/i);
    expect(screen.queryByTestId("guardrail-note")).not.toBeInTheDocument();
    unmount();

    render(<SummaryCards result={flexed} spendingRule="guardrails" />);
    expect(screen.getByTestId("guardrail-note")).toHaveTextContent("planned cuts");
    expect(screen.getByTestId("guardrail-note")).toHaveTextContent("could not fund");
  });

  it("a deterministic run shows no market statistics, though it stores one path", () => {
    const det = {
      ...fixtureResult,
      monte_carlo_runs: 0,
      winning_policy: {
        ...fixtureResult.winning_policy, success_probability: 1, monte_carlo_paths: 1,
        mean_years_reduced: 2,
      },
    };
    render(<SummaryCards result={det} />);
    const success = screen.getByTestId("card-success");
    expect(success).toHaveTextContent("—");
    expect(success).toHaveTextContent("No market simulation");
    expect(success).not.toHaveTextContent("100%");
    expect(success).not.toHaveTextContent("±");
    expect(screen.getByTestId("card-score")).toHaveTextContent("After-tax estate minus spending-shortfall penalties.");
    expect(screen.getByTestId("card-score")).toHaveTextContent("Today's dollars · steady-return projection");
    expect(screen.queryByTestId("card-note")).not.toBeInTheDocument();
  });

  it("says nothing about cuts when spending always met target", () => {
    const clean = {
      ...fixtureResult,
      winning_policy: { ...fixtureResult.winning_policy, mean_years_reduced: 0 },
    };
    render(<SummaryCards result={clean} />);
    expect(screen.queryByTestId("card-note")).not.toBeInTheDocument();
  });

  it("says nothing on runs stored before dynamic spending shipped", () => {
    render(<SummaryCards result={fixtureResult} />);
    expect(screen.queryByTestId("card-note")).not.toBeInTheDocument();
  });
});

describe("YearTable", () => {
  // Bracket room used to surface only inside a conversion year's narrative,
  // so a year with unused room and no conversion showed it nowhere.
  it("shows the bracket room left for every year", () => {
    const rows = [
      makeRow(2028, {
        rationale: makeRationale({
          bracket: {
            bracket_rate: 0.12,
            bracket_top: 100800,
            headroom_used: 0,
            headroom_remaining: 33000,
          },
        }),
      }),
      makeRow(2029, {
        rationale: makeRationale({
          bracket: {
            bracket_rate: 0.37,
            bracket_top: null,
            headroom_used: 0,
            headroom_remaining: 0,
          },
        }),
      }),
    ];
    render(<YearTable rows={rows} />);
    expect(
      screen.getByRole("columnheader", { name: /bracket room/i })
    ).toBeInTheDocument();
    const cell = screen.getByTestId("bracket-room-2028");
    expect(cell).toHaveTextContent("$33,000");
    expect(cell).toHaveTextContent("left in 12%");
    // Top bracket: no ceiling, so no room figure.
    expect(screen.getByTestId("bracket-room-2029")).toHaveTextContent("—");
  });

  it("renders a row per year", () => {
    render(<YearTable rows={fixtureResult.yearly_plan} />);
    expect(screen.getByTestId("year-row-2025")).toBeInTheDocument();
    expect(screen.getByTestId("year-row-2026")).toBeInTheDocument();
    expect(screen.getByTestId("year-row-2027")).toBeInTheDocument();
  });

  it("links a taxable-withdrawal year to the sale planner with a purpose split", () => {
    const convRationale = makeRationale({
      conversion: {
        action_id: "fill_22",
        amount: 160000,
        target_description: "fills the 22% bracket",
        counterfactual_none_tax: 400,
        marginal_cost_rate: 0.27,
        betr: 0.27,
        projected_future_marginal_rate: 0.24,
        betr_verdict: "unfavorable",
      },
    });
    const row = makeRow(2029, {
      conversion: 160000,
      withdrawal_taxable: 43590,
      total_tax: 13000,
      rationale: convRationale,
    });
    render(<YearTable rows={[row]} />);
    fireEvent.click(screen.getByTestId("year-row-2029"));

    // Purpose split: conversion tax = min(43590, 13000 − 400) = 12,600
    expect(screen.getByText(/\$30,990 funds spending/)).toBeInTheDocument();
    expect(
      screen.getByText(/\$12,600 funds Roth conversion taxes/)
    ).toBeInTheDocument();
    // The inline planner offers a "Plan this sale" button (no navigation).
    expect(
      screen.getByRole("button", { name: /plan this sale/i })
    ).toBeInTheDocument();
  });

  it("each year has a visible, keyboard-reachable expand control", () => {
    const row = makeRow(2030, { withdrawal_taxable: 25000 });
    render(<YearTable rows={[row]} />);
    const toggle = screen.getByTestId("year-toggle-2030");
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("rationale-2030")).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(document.getElementById("rationale-2030")).not.toBeInTheDocument();
  });

  it("shows the inline planner for a plain withdrawal year, no conversion split", () => {
    const row = makeRow(2030, { withdrawal_taxable: 25000 });
    render(<YearTable rows={[row]} />);
    fireEvent.click(screen.getByTestId("year-row-2030"));

    expect(
      screen.getByRole("button", { name: /plan this sale/i })
    ).toBeInTheDocument();
    expect(screen.queryByText(/conversion taxes/)).not.toBeInTheDocument();
  });

  it("shows no sale planner when the year has no taxable withdrawal", () => {
    const row = makeRow(2030, { withdrawal_taxable: 0 });
    render(<YearTable rows={[row]} />);
    fireEvent.click(screen.getByTestId("year-row-2030"));

    expect(
      screen.queryByRole("button", { name: /plan this sale/i })
    ).not.toBeInTheDocument();
  });

  it("offers the planner only on the first withdrawal year; later years get a note", () => {
    const rows = [
      makeRow(2026, { withdrawal_taxable: 0 }),
      makeRow(2027, { withdrawal_taxable: 30000 }),
      makeRow(2028, { withdrawal_taxable: 20000 }),
    ];
    render(<YearTable rows={rows} />);

    // First actionable year (2027): the interactive planner.
    fireEvent.click(screen.getByTestId("year-row-2027"));
    expect(
      screen.getByRole("button", { name: /plan this sale/i })
    ).toBeInTheDocument();
    expect(screen.queryByTestId("sale-note-2027")).not.toBeInTheDocument();

    // Later withdrawal year (2028): a re-run note, no planner button.
    fireEvent.click(screen.getByTestId("year-row-2028"));
    expect(screen.getByTestId("sale-note-2028")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /plan this sale/i })
    ).not.toBeInTheDocument();
  });

  it("blanks a person's age past their plan-to age", () => {
    const rows = [
      { ...fixtureResult.yearly_plan[0], year: 2025, age_self: 84, age_spouse: 80 },
      { ...fixtureResult.yearly_plan[0], year: 2026, age_self: 85, age_spouse: 81 },
      { ...fixtureResult.yearly_plan[0], year: 2027, age_self: 86, age_spouse: 82 },
    ];
    render(<YearTable rows={rows} selfDeathAge={85} spouseDeathAge={81} />);

    // In-plan ages still render
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText("81")).toBeInTheDocument();
    // Past plan-to age: blank, not the raw simulated age
    expect(screen.queryByText("86")).not.toBeInTheDocument();
    expect(screen.queryByText("82")).not.toBeInTheDocument();
  });

  it("clicking a row reveals the narrative text", () => {
    render(<YearTable rows={fixtureResult.yearly_plan} />);
    // narrative not visible yet
    expect(
      screen.queryByText("Converting $30,000 to fill the 22% bracket.")
    ).not.toBeInTheDocument();

    // click the 2026 row
    fireEvent.click(screen.getByTestId("year-row-2026"));

    // narrative now visible
    expect(
      screen.getByText("Converting $30,000 to fill the 22% bracket.")
    ).toBeInTheDocument();
  });

  it("clicking the same row again collapses it", () => {
    render(<YearTable rows={fixtureResult.yearly_plan} />);
    const row = screen.getByTestId("year-row-2026");
    fireEvent.click(row);
    expect(
      screen.getByText("Converting $30,000 to fill the 22% bracket.")
    ).toBeInTheDocument();
    fireEvent.click(row);
    expect(
      screen.queryByText("Converting $30,000 to fill the 22% bracket.")
    ).not.toBeInTheDocument();
  });

  it("shows a Funded By breakdown of withdrawal sources per year", () => {
    const mixed = makeRow(2028, {
      withdrawal_taxable: 40000,
      withdrawal_traditional: 25000,
      withdrawal_roth: 0,
    });
    render(<YearTable rows={[mixed]} />);

    const cell = screen.getByTestId("funded-by-2028");
    expect(cell).toHaveTextContent("Taxable $40k");
    expect(cell).toHaveTextContent("IRA $25k");
    expect(cell).not.toHaveTextContent("Roth");
  });

  it("shows a dash when nothing was withdrawn that year", () => {
    const none = makeRow(2029, {
      withdrawal_taxable: 0,
      withdrawal_traditional: 0,
      withdrawal_roth: 0,
    });
    render(<YearTable rows={[none]} />);
    expect(screen.queryByTestId("funded-by-2029")).not.toBeInTheDocument();
  });

  // The plan now runs to the full horizon even after the money runs out, so
  // some rows can show less spendable cash than the plan needs. Silently
  // printing a small number would read as a rounding oddity rather than the
  // year the household cannot pay for.
  it("flags a year that could not fund required spending", () => {
    const short = makeRow(2040, {
      net_spendable: 42000,
      required_spending: 90000,
      shortfall: 48000,
    });
    render(<YearTable rows={[short]} />);

    const cell = screen.getByTestId("shortfall-2040");
    expect(cell).toHaveTextContent("$48,000 short");
    expect(cell).toHaveTextContent("$42,000");
  });

  it("does not flag a funded year", () => {
    const funded = makeRow(2041, {
      net_spendable: 90000,
      required_spending: 90000,
      shortfall: 0,
    });
    render(<YearTable rows={[funded]} />);
    expect(screen.queryByTestId("shortfall-2041")).not.toBeInTheDocument();
  });

  it("does not flag rows from runs stored before shortfalls were tracked", () => {
    const legacy = makeRow(2042, { net_spendable: 42000, required_spending: 90000 });
    delete (legacy as { shortfall?: number }).shortfall;
    render(<YearTable rows={[legacy]} />);
    expect(screen.queryByTestId("shortfall-2042")).not.toBeInTheDocument();
  });

  // A guardrail cut is NOT a shortfall - the plan funded what it set out to
  // fund. But it is still spending the household gave up, so the row must say
  // so rather than quietly lowering the bar it is being judged against.
  it("shows spending the guardrails gave up", () => {
    const trimmed = makeRow(2035, {
      net_spendable: 108000,
      required_spending: 108000,
      target_spending: 130000,
      discretionary_cut: 22000,
      shortfall: 0,
    });
    render(<YearTable rows={[trimmed]} />);

    const cell = screen.getByTestId("spending-cut-2035");
    expect(cell).toHaveTextContent("$22,000 below target");
    // Not dressed up as a failure - it is a different thing.
    expect(screen.queryByTestId("shortfall-2035")).not.toBeInTheDocument();
  });

  it("prefers the shortfall flag when a year is both cut and unfunded", () => {
    const both = makeRow(2036, {
      net_spendable: 70000,
      required_spending: 108000,
      target_spending: 130000,
      discretionary_cut: 22000,
      shortfall: 38000,
    });
    render(<YearTable rows={[both]} />);
    expect(screen.getByTestId("shortfall-2036")).toHaveTextContent(
      "$38,000 short",
    );
  });

  it("shows nothing extra under the default fixed-spending rule", () => {
    const plain = makeRow(2037, {
      net_spendable: 130000,
      required_spending: 130000,
      target_spending: 130000,
      discretionary_cut: 0,
      shortfall: 0,
    });
    render(<YearTable rows={[plain]} />);
    expect(screen.queryByTestId("spending-cut-2037")).not.toBeInTheDocument();
    expect(screen.queryByTestId("shortfall-2037")).not.toBeInTheDocument();
  });
});

describe("RationalePanel", () => {
  it("renders the narrative", () => {
    render(<RationalePanel rationale={rowWithConversion.rationale} />);
    expect(
      screen.getByText("Converting $30,000 to fill the 22% bracket.")
    ).toBeInTheDocument();
  });

  it("renders a red badge for a crossed threshold (distance < 0)", () => {
    render(<RationalePanel rationale={rowWithConversion.rationale} />);
    const redBadges = screen.getAllByTestId("warning-red");
    expect(redBadges.length).toBeGreaterThan(0);
    expect(redBadges[0]).toHaveTextContent("IRMAA Tier 1 surcharge applies");
  });

  it("renders an amber badge when distance > 0", () => {
    const rationaleWithAmber = makeRationale({
      warnings: [
        {
          kind: "niit",
          threshold: 250000,
          distance: 5000, // not yet crossed
          consequence: "Approaching NIIT threshold",
        },
      ],
    });
    render(<RationalePanel rationale={rationaleWithAmber} />);
    const amberBadges = screen.getAllByTestId("warning-amber");
    expect(amberBadges.length).toBeGreaterThan(0);
    expect(amberBadges[0]).toHaveTextContent("Approaching NIIT threshold");
  });

  it("renders BETR as a neutral single-year break-even, no verdict word", () => {
    render(<RationalePanel rationale={rowWithConversion.rationale} />);
    expect(screen.getByText(/single-year break-even/)).toBeInTheDocument();
    expect(screen.getByText(/chosen on lifetime totals/)).toBeInTheDocument();
    // The favorable/unfavorable judgment word is no longer shown.
    expect(screen.queryByText(/unfavorable/)).not.toBeInTheDocument();
  });

  it("shows the all-in cost per dollar converted", () => {
    // The conversion's true cost carries state tax, IRMAA, and the extra
    // Social Security it drags into taxable income, so it routinely exceeds
    // the bracket the conversion nominally sits in. The value existed in the
    // payload but was never displayed.
    render(<RationalePanel rationale={rowWithConversion.rationale} />);
    expect(screen.getByTestId("conversion-cost-rate")).toHaveTextContent("22.0%");
    expect(screen.getByText(/per dollar converted/)).toBeInTheDocument();
  });

  it("does not render the conversion cost when there is no conversion", () => {
    const noConv = makeRationale({ conversion: null });
    render(<RationalePanel rationale={noConv} />);
    expect(screen.queryByTestId("conversion-cost-rate")).not.toBeInTheDocument();
  });

  it("does not render BETR line when no conversion", () => {
    const noConv = makeRationale({ conversion: null });
    render(<RationalePanel rationale={noConv} />);
    expect(screen.queryByText(/single-year break-even/)).not.toBeInTheDocument();
  });
});

describe("result.warnings list", () => {
  it("renders top-level result warnings", () => {
    render(
      <div>
        {fixtureResult.warnings.map((w, i) => (
          <Alert key={i} variant="destructive">
            <AlertDescription>{w}</AlertDescription>
          </Alert>
        ))}
      </div>
    );
    expect(
      screen.getByText("Portfolio may be insufficient for a 30-year horizon")
    ).toBeInTheDocument();
  });
});

describe("AlternativesTable — scenario count", () => {
  const alt = [
    {
      policy_id: "fill_32",
      lifetime_taxes_delta: -2855,
      terminal_estate_delta: -1802,
      success_probability_delta: 0,
    },
  ];

  // The count was hardcoded at 100 — the old default — while runs used 300.
  it("states the run's own scenario count", () => {
    render(
      <AlternativesTable
        alternatives={alt}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.54}
        monteCarloRuns={300}
      />
    );
    const table = screen.getByTestId("alternatives-table");
    expect(table).toHaveTextContent("across 300 market scenarios");
    expect(table).not.toHaveTextContent("100 market scenarios");
  });

  it("says the simulation was skipped when the run used none", () => {
    render(
      <AlternativesTable
        alternatives={alt}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.54}
        monteCarloRuns={0}
      />
    );
    const table = screen.getByTestId("alternatives-table");
    expect(table).not.toHaveTextContent("market scenarios");
    expect(table).toHaveTextContent("market simulation was skipped");
  });
});

describe("AlternativesTable — ranked on the simulation", () => {
  const alt = (s: number, p: number, tax: number, estate: number, mean: number,
               verdict: "unresolved" | "winner" = "unresolved"): AlternativePolicy => ({
    policy_id: "none", key: `none@${s}-${p}`, claim_age_self: s, claim_age_spouse: p,
    lifetime_taxes_delta: tax, terminal_estate_delta: estate, success_probability_delta: -0.0033,
    monte_carlo_paths: 300, score: 3_000_820 - mean, year0_conversion: 0,
    paired: { verdict, mean_difference: mean, ci_low: -5000, ci_high: 9000 } as AlternativePolicy["paired"],
  });
  const alternatives = [alt(68, 67, -16_710, 34_568, 2_206), alt(68, 66, -20_116, 34_642, 2_326),
                        alt(68, 65, -11_340, 7_266, 13_660, "winner")];
  const result = {
    status: "success", computation_time_seconds: 1, paths_evaluated: 1, monte_carlo_runs: 300,
    search: { mode: "joint" },
    winning_policy: {
      policy_id: "none", key: "none@69-68", claim_age_self: 69, claim_age_spouse: 68,
      lifetime_taxes_nominal: 0, lifetime_taxes_pv: 0, terminal_estate: 0, success_probability: 0.98,
      monte_carlo_paths: 300, score: 3_000_820, total_conversions: 0, year0_conversion: 0,
      projected_future_marginal_rate: 0.22,
    },
    yearly_plan: [], alternative_policies: alternatives, warnings: [],
  } as unknown as OptimizationResult;

  const renderRanked = () =>
    render(
      <AlternativesTable
        alternatives={alternatives}
        winningPolicyId="none"
        winnerSuccessProbability={0.98}
        monteCarloRuns={300}
        firstYear={2026}
        winnerYear0Conversion={0}
        ranking={rankingRows(result)}
        closeCall={confidenceSentence(result)}
        steadyReturn={0.06}
      />
    );

  it("leads with the scores that chose the recommendation", () => {
    renderRanked();
    const table = screen.getByTestId("ranking-table");
    const rec = screen.getByTestId("ranking-recommendation");
    expect(rec).toHaveTextContent("Recommendation");
    expect(rec).toHaveTextContent("highest average score");
    expect(rec).toHaveTextContent("$3,000,820");
    expect(rec).toHaveTextContent("294 of 300");
    const close = screen.getByTestId("ranking-row-none@68-67");
    expect(close).toHaveTextContent("$2,998,614");
    expect(close).toHaveTextContent("−$2,206");
    expect(close).toHaveTextContent("293 of 300");
    expect(close).toHaveTextContent("Too close to distinguish");
    // The steady-return tax and estate figures are not in the main table.
    expect(table).not.toHaveTextContent("$16,710");
    // Every strategy converts $0 this year: no column of zeros.
    expect(table).not.toHaveTextContent("Roth conversion in 2026");
    expect(screen.getByTestId("close-call")).toHaveTextContent(
      "Ages 69 / 68 have the highest average modeled score. However, this simulation cannot " +
      "clearly separate them from ages 68 / 67 or 68 / 66."
    );
  });

  it("keeps the steady-return taxes and estate in a disclosure, labelled with the run's return", () => {
    renderRanked();
    const steady = screen.getByTestId("steady-comparison");
    expect(steady.tagName).toBe("DETAILS");
    expect(steady).not.toHaveAttribute("open");
    expect(steady).toHaveTextContent("Compare taxes and estate assuming a steady 6% return");
    expect(steady).toHaveTextContent("every year earns exactly 6%");
    expect(steady).toHaveTextContent("-$16,710");
    expect(steady).toHaveTextContent("+$34,568");
    expect(steady).toHaveTextContent("These figures did not decide the ranking above.");
  });

  it("explains the comparison labels beside the table, statistics under Technical details", () => {
    render(
      <AlternativesTable
        alternatives={alternatives}
        winningPolicyId="none"
        winnerSuccessProbability={0.98}
        monteCarloRuns={300}
        ranking={rankingRows(result)}
        materiality={6250}
      />
    );
    const legend = screen.getByTestId("verdict-details");
    expect(legend).toHaveTextContent(
      "Practically equivalent: The results are similar enough to treat these options alike"
    );
    expect(legend).toHaveTextContent(
      "Too close to distinguish: These simulations don’t give us enough evidence to say which option is better."
    );
    expect(legend).toHaveTextContent("Recommendation ahead: These simulations provide evidence favoring the recommendation.");
    expect(legend).toHaveTextContent("Alternative ahead: These simulations provide evidence favoring the alternative.");
    const technical = screen.getByTestId("verdict-technical");
    expect(technical.tagName).toBe("DETAILS");
    expect(technical).toHaveTextContent("within ±$6,250");
    expect(technical).toHaveTextContent("median");
  });

  it("says when a strategy set aside early rests on fewer scenarios", () => {
    const early = { ...alternatives[2], score: undefined, monte_carlo_paths: 100 };
    const ranking = rankingRows({ ...result, alternative_policies: [alternatives[0], early] })!;
    expect(ranking[2]).toMatchObject({ score: null, scenarios: 100, difference: -13_660 });
    render(
      <AlternativesTable alternatives={[alternatives[0], early]} winningPolicyId="none"
                         winnerSuccessProbability={0.98} monteCarloRuns={300} ranking={ranking} />
    );
    expect(screen.getByTestId("fewer-scenarios")).toHaveTextContent("scored on fewer market scenarios");
  });

  it("shows the conversion column when a strategy converts this year", () => {
    const converting = { ...alternatives[2], policy_id: "level_5pct_annual", year0_conversion: 40_000 };
    render(
      <AlternativesTable
        alternatives={[converting]}
        winningPolicyId="none"
        winnerSuccessProbability={0.98}
        monteCarloRuns={300}
        firstYear={2026}
        ranking={rankingRows({ ...result, alternative_policies: [converting] })}
      />
    );
    expect(screen.getByTestId("conversion-column")).toHaveTextContent("Roth conversion in 2026");
    expect(screen.getByTestId("year0-cell-level_5pct_annual")).toHaveTextContent("$40,000");
  });
});

describe("AlternativesTable — Success shown as absolute probability", () => {
  it("a 0.0 success delta renders the winner's probability, not 0%", () => {
    render(
      <AlternativesTable
        alternatives={[
          {
            policy_id: "fill_32",
            lifetime_taxes_delta: -2855,
            terminal_estate_delta: -1802,
            success_probability_delta: 0,
          },
        ]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.54}
      />
    );
    const table = screen.getByTestId("alternatives-table");
    // The exact confusion this fixes: same success as the winner reads as
    // "54%", never "0.0%".
    expect(table).toHaveTextContent("54%");
    expect(table).not.toHaveTextContent("0.0%");
  });

  it("a positive delta adds to the winner's probability", () => {
    render(
      <AlternativesTable
        alternatives={[
          {
            policy_id: "level_25",
            lifetime_taxes_delta: 111681,
            terminal_estate_delta: 215786,
            success_probability_delta: 0.1,
          },
        ]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.54}
      />
    );
    // 0.54 + 0.10 = 0.64 → 64%
    expect(screen.getByTestId("alternatives-table")).toHaveTextContent("64%");
  });
});

describe("AlternativesTable — paired verdict", () => {
  const base = {
    policy_id: "level_100",
    lifetime_taxes_delta: -1000,
    terminal_estate_delta: 2000,
    success_probability_delta: 0,
  };
  const paired = {
    verdict: "unresolved" as const,
    mean_difference: 5234,
    median_difference: -415,
    std_error: 4283,
    ci_low: -3161,
    ci_high: 13629,
    winner_win_fraction: 0.5,
    both_feasible: 67,
    winner_only_feasible: 0,
    alternative_only_feasible: 0,
    both_infeasible: 33,
    both_feasible_mean_difference: 20651,
  };

  it("flags an unresolved comparison so a coin-flip isn't shown as a ranking", () => {
    render(
      <AlternativesTable
        alternatives={[{ ...base, paired }]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.67}
      />
    );
    expect(screen.getByTestId("verdict-unresolved")).toHaveTextContent("Too close to distinguish");
  });

  it("labels every verdict in the shared vocabulary", () => {
    const verdicts = [
      ["winner", "Recommendation ahead"],
      ["alternative", "Alternative ahead"],
      ["equivalent", "Practically equivalent"],
    ] as const;
    for (const [verdict, label] of verdicts) {
      const { unmount } = render(
        <AlternativesTable
          alternatives={[{ ...base, paired: { ...paired, verdict } }]}
          winningPolicyId="fill_24"
          winnerSuccessProbability={0.67}
        />
      );
      expect(screen.getByTestId(`verdict-${verdict}`)).toHaveTextContent(label);
      // Never "lost to": a close call is not a defeat.
      expect(screen.getByTestId("alternatives-table")).not.toHaveTextContent(/lost to/i);
      unmount();
    }
  });

  it("does not flag a decisive comparison", () => {
    render(
      <AlternativesTable
        alternatives={[{ ...base, paired: { ...paired, verdict: "winner" as const } }]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.67}
      />
    );
    expect(screen.queryByTestId("verdict-unresolved")).not.toBeInTheDocument();
  });

  it("renders runs that predate paired comparison", () => {
    render(
      <AlternativesTable
        alternatives={[base]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.67}
      />
    );
    expect(screen.queryByTestId("verdict-unresolved")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// strategyOptions — the strategy picker must match the household's inputs
// ---------------------------------------------------------------------------
//
// REGRESSION: the What-if Strategy dropdown offered every policy label
// regardless of the household, so picking "Fill the 12% bracket (greedy)" on a
// household whose salary already exceeds that bracket returned HTTP 400 after
// the user clicked Compare. The greedy fill_12 is never generated for those
// inputs — only fill_12_annual is.

describe("strategyOptions", () => {
  it("offers only the policies the optimizer can run", () => {
    const available = ["defer_1yr", "fill_10_annual", "fill_12_annual", "none"];
    const ids = strategyOptions(available).map(([id]) => id);

    expect(ids).toContain("fill_12_annual");
    expect(ids).not.toContain("fill_12");
    expect(ids).not.toContain("fill_24");
    expect(ids.every((id) => available.includes(id))).toBe(true);
  });

  it("shows everything when availability is unknown", () => {
    // Empty means "still loading" or "lookup failed" — a best-effort call must
    // not leave the user with an empty menu.
    expect(strategyOptions([]).length).toBe(
      Object.keys(POLICY_LABELS).length,
    );
  });

  it("returns labels, not bare ids", () => {
    const opts = strategyOptions(["fill_12_annual"]);
    expect(opts).toEqual([["fill_12_annual", "Fill the 12% bracket every year"]]);
  });

  it("offers limited-duration rules, named from their id", () => {
    // Their stop years depend on the household, so no fixed map can list them.
    const opts = strategyOptions(["fill_22_thru_2031", "none", "fill_22_thru_2028"]);
    expect(opts).toEqual([
      ["none", "No conversions"],
      ["fill_22_thru_2028", "Fill the 22% bracket through 2028"],
      ["fill_22_thru_2031", "Fill the 22% bracket through 2031"],
    ]);
  });
});

describe("policyLabel", () => {
  it("still names greedy policies from runs saved before they were removed", () => {
    expect(policyLabel("fill_24")).toBe("Fill the 24% bracket (greedy)");
    expect(strategyOptions([]).map(([id]) => id)).not.toContain("fill_24");
  });

  it("names limited-duration rules and leaves unknown ids alone", () => {
    expect(policyLabel("fill_12_thru_2030")).toBe("Fill the 12% bracket through 2030");
    expect(policyLabel("fill_12_annual")).toBe("Fill the 12% bracket every year");
    expect(policyLabel("mystery")).toBe("mystery");
    expect(policyLabel("level_5pct_annual")).toBe("Convert up to 5% of the starting IRA every year");
    expect(policyLabel("level_10pct_thru_2029")).toBe(
      "Convert up to 10% of the starting IRA each year through 2029",
    );
  });
});

// ---------------------------------------------------------------------------
// AlternativesTable — this year's conversion and the spread across close calls
// ---------------------------------------------------------------------------
//
// Close strategies agree on roughly how much to convert in total but can
// disagree by hundreds of thousands on how much to convert NOW — the one
// number a user acts on before re-running next year.

describe("AlternativesTable — this year's conversion", () => {
  const unresolved = {
    verdict: "unresolved" as const,
    mean_difference: 5234,
    median_difference: -415,
    std_error: 4283,
    ci_low: -3161,
    ci_high: 13629,
    winner_win_fraction: 0.5,
    both_feasible: 67,
    winner_only_feasible: 0,
    alternative_only_feasible: 0,
    both_infeasible: 33,
    both_feasible_mean_difference: 20651,
  };
  const row = (policy_id: string, year0: number, verdict: "unresolved" | "winner") => ({
    policy_id,
    lifetime_taxes_delta: 1000,
    terminal_estate_delta: -2000,
    success_probability_delta: 0,
    year0_conversion: year0,
    total_conversions: 630000,
    paired: { ...unresolved, verdict },
  });

  it("shows each strategy's own conversion this year", () => {
    render(
      <AlternativesTable
        alternatives={[row("level_100", 500000, "winner")]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.9}
        winnerYear0Conversion={396000}
        firstYear={2026}
      />
    );
    // Named by the saved projection's year, with what it means.
    const heading = screen.getByTestId("conversion-column");
    expect(heading).toHaveTextContent("Roth conversion in 2026");
    expect(heading).toHaveAttribute(
      "title", "Amount transferred from traditional retirement accounts to Roth accounts in 2026.");
    expect(screen.getByText("$500,000")).toBeInTheDocument();
  });

  it("states the range across strategies too close to call, winner included", () => {
    render(
      <AlternativesTable
        alternatives={[
          row("fill_12_annual", 98000, "unresolved"),
          row("fill_32", 503000, "unresolved"),
          row("fill_22", 1000000, "winner"), // decisive: not part of the range
        ]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.9}
        winnerYear0Conversion={396000}
      />
    );
    const note = screen.getByTestId("year0-spread");
    expect(note).toHaveTextContent("$396,000");
    expect(note).toHaveTextContent("$98,000 to $503,000");
    expect(note).not.toHaveTextContent("$1,000,000");
  });

  it("says nothing about a spread when every comparison is decisive", () => {
    render(
      <AlternativesTable
        alternatives={[row("fill_32", 503000, "winner")]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.9}
        winnerYear0Conversion={396000}
      />
    );
    expect(screen.queryByTestId("year0-spread")).not.toBeInTheDocument();
  });

  it("shows a dash, not $0, on runs saved before the field existed", () => {
    render(
      <AlternativesTable
        alternatives={[
          {
            policy_id: "none",
            lifetime_taxes_delta: 1000,
            terminal_estate_delta: -2000,
            success_probability_delta: 0,
            paired: unresolved,
          },
        ]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.9}
        winnerYear0Conversion={396000}
      />
    );
    expect(screen.getByTestId("year0-cell-none")).toHaveTextContent("—");
    expect(screen.queryByTestId("year0-spread")).not.toBeInTheDocument();
  });
});

describe("AlternativesTable — optimizer's pick on a forced run", () => {
  it("tags the row the optimizer itself chose", () => {
    render(
      <AlternativesTable
        alternatives={[
          { policy_id: "none", lifetime_taxes_delta: 0, terminal_estate_delta: 0, success_probability_delta: 0 },
          { policy_id: "fill_22", lifetime_taxes_delta: 0, terminal_estate_delta: 0, success_probability_delta: 0 },
        ]}
        winningPolicyId="fill_10_annual"
        winnerSuccessProbability={0.9}
        optimizerPickId="none"
      />
    );
    // A pinned plan did not beat the optimizer's pick, so nothing "lost to" it.
    expect(screen.getByTestId("alternatives-table")).not.toHaveTextContent(/lost to/i);
    expect(screen.getByTestId("alternatives-table")).toHaveTextContent(/the plan you chose to run/i);
    const tags = screen.getAllByTestId("optimizer-pick-tag");
    expect(tags).toHaveLength(1);
    expect(tags[0].closest("tr")).toHaveTextContent("No conversions");
  });
});

describe("AlternativesTable — close strategies that all wait", () => {
  const unresolved = {
    verdict: "unresolved" as const,
    mean_difference: 1, median_difference: 1, std_error: 1, ci_low: -1, ci_high: 1,
    winner_win_fraction: 0.5, both_feasible: 1, winner_only_feasible: 0,
    alternative_only_feasible: 0, both_infeasible: 0, both_feasible_mean_difference: 1,
  };
  const alt = (policy_id: string, first: number | null, verdict = "unresolved" as const) => ({
    policy_id,
    lifetime_taxes_delta: 0,
    terminal_estate_delta: 0,
    success_probability_delta: 0,
    year0_conversion: 0,
    total_conversions: first ? 100000 : 0,
    first_conversion_year: first,
    paired: { ...unresolved, verdict },
  });

  it("says nothing converts this year and when each close strategy starts", () => {
    render(
      <AlternativesTable
        alternatives={[alt("fill_10_annual", 2029), alt("defer_1yr", 2028)]}
        winningPolicyId="none"
        winnerSuccessProbability={0.9}
        winnerYear0Conversion={0}
        winnerFirstConversionYear={null}
      />
    );
    const note = screen.getByTestId("year0-all-wait");
    expect(note).toHaveTextContent(/none of them converts anything this year/i);
    expect(note).toHaveTextContent("Fill the 10% bracket every year: from 2029");
    expect(note).toHaveTextContent("Skip year 1, then convert (greedy): from 2028");
    expect(note).toHaveTextContent("No conversions: never");
    expect(screen.queryByTestId("year0-spread")).not.toBeInTheDocument();
  });

  it("stays quiet when no comparison is close", () => {
    render(
      <AlternativesTable
        alternatives={[alt("fill_10_annual", 2029, "winner" as never)]}
        winningPolicyId="none"
        winnerSuccessProbability={0.9}
        winnerYear0Conversion={0}
        winnerFirstConversionYear={null}
      />
    );
    expect(screen.queryByTestId("year0-all-wait")).not.toBeInTheDocument();
  });
});

describe("AlternativesTable — paths funding spending", () => {
  it("does not colour two shares that read the same as better or worse", () => {
    render(
      <AlternativesTable
        alternatives={[{
          policy_id: "none", lifetime_taxes_delta: 0, terminal_estate_delta: 0,
          success_probability_delta: -0.003,
        }]}
        winningPolicyId="fill_24"
        winnerSuccessProbability={0.98}
      />
    );
    const cell = screen.getByText("98%");
    expect(cell.className).toMatch(/text-muted-foreground/);
    expect(cell.className).not.toMatch(/destructive/);
  });
});

describe("AlternativesTable without a market simulation", () => {
  it("shows no comparison labels or notes that depend on them", () => {
    render(
      <AlternativesTable
        alternatives={[
          {
            policy_id: "fill_10_thru_2029",
            lifetime_taxes_delta: 2000,
            terminal_estate_delta: -10000,
            success_probability_delta: 0,
            year0_conversion: 5000,
            paired: { verdict: "equivalent" },
          } as unknown as AlternativePolicy,
        ]}
        winningPolicyId="none"
        winnerSuccessProbability={1}
        monteCarloRuns={0}
        winnerYear0Conversion={0}
        winnerFirstConversionYear={null}
      />,
    );
    expect(screen.queryByText("Practically equivalent")).not.toBeInTheDocument();
    expect(screen.queryByTestId("year0-spread")).not.toBeInTheDocument();
    expect(screen.queryByText(/Each badge says/)).not.toBeInTheDocument();
  });
});

describe("MarketExplanation", () => {
  it("states the run's recorded assumptions, never fixed numbers", () => {
    render(<MarketExplanation market={{ scenarios: 300, meanReturn: 0.055, volatility: 0.1 }} />);
    const box = screen.getByTestId("market-explanation");
    expect(box).toHaveTextContent("How we simulate market outcomes");
    expect(box).toHaveTextContent("under 300 possible investment-return scenarios");
    expect(box).toHaveTextContent("assumed average annual return of 5.5%");
    expect(screen.getByTestId("market-technical")).toHaveTextContent(
      "Annual volatility is 10 percentage points, measured as the standard deviation of annual returns.");
    expect(box).toHaveTextContent("projection assuming a steady 5.5% annual return");
  });

  it("leaves an unrecorded volatility unstated, and says when nothing was simulated", () => {
    const { rerender } = render(
      <MarketExplanation market={{ scenarios: 300, meanReturn: 0.06, volatility: null }} />);
    expect(screen.queryByTestId("market-technical")).not.toBeInTheDocument();
    rerender(<MarketExplanation market={{ scenarios: 0, meanReturn: 0.06, volatility: null }} />);
    const box = screen.getByTestId("market-explanation");
    expect(box).toHaveTextContent("No market simulation");
    expect(box).not.toHaveTextContent("scenarios under");
  });
});

describe("AlternativesTable explanations", () => {
  const none = {
    policy_id: "none", lifetime_taxes_delta: 1000, terminal_estate_delta: -2000,
    success_probability_delta: 0, year0_conversion: 0,
  } as unknown as AlternativePolicy;

  it("explains rule names only when a rule is shown", () => {
    const { rerender } = render(
      <AlternativesTable alternatives={[none]} winningPolicyId="none"
        winnerSuccessProbability={0.9} monteCarloRuns={300} firstYear={2026} />);
    expect(screen.getByTestId("alternatives-table")).not.toHaveTextContent("through YYYY");
    rerender(
      <AlternativesTable alternatives={[{ ...none, policy_id: "fill_12_thru_2030" }]}
        winningPolicyId="none" winnerSuccessProbability={0.9} monteCarloRuns={300} firstYear={2026} />);
    expect(screen.getByTestId("alternatives-table")).toHaveTextContent("through YYYY");
  });

  it("leads with how to read the columns; the method sits under How these comparisons work", () => {
    render(
      <AlternativesTable alternatives={[none]} winningPolicyId="none"
        winnerSuccessProbability={0.9} monteCarloRuns={300} firstYear={2026} />);
    expect(screen.getByTestId("alternatives-table")).toHaveTextContent(
      "Compare these alternatives with the recommendation. Negative tax amounts mean less tax; " +
      "positive estate amounts mean more left to heirs. The conversion column shows the amount " +
      "to convert, not a difference.");
    expect(screen.getByTestId("comparisons-explainer")).toHaveTextContent(
      "chosen by its modeled score across 300 market scenarios");
  });
});

describe("level-dollar strategy names", () => {
  it("name the yearly amount once the starting balance is known", () => {
    expect(policyLabel("level_5pct_thru_2029", 1_000_000)).toBe("Convert up to $50,000 annually through 2029");
    expect(policyLabel("level_20pct_annual", 1_234_567)).toBe("Convert up to $246,913 annually");
    // Runs saved before the balance was recorded keep the percentage.
    expect(policyLabel("level_5pct_thru_2029")).toBe("Convert up to 5% of the starting IRA each year through 2029");
    expect(strategyOptions(["level_10pct_annual"], 500_000)).toContainEqual(
      ["level_10pct_annual", "Convert up to $50,000 annually"]);
    // Smaller amounts first, as numbers rather than as text.
    expect(strategyOptions(["level_10pct_annual", "level_5pct_thru_2030", "level_5pct_annual"], 500_000)
      .map(([, label]) => label).slice(-3)).toEqual([
      "Convert up to $25,000 annually", "Convert up to $25,000 annually through 2030",
      "Convert up to $50,000 annually"]);
  });
});
