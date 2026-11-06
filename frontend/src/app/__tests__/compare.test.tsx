/**
 * @jest-environment jsdom
 *
 * RTL tests for the Compare page (src/app/compare/page.tsx).
 *
 * TDD RED phase — written before implementation.
 *
 * Coverage:
 *  (1) Renders the household selector and constraint form fields.
 *  (2) Mocked compareScenarios call → delta cards show formatted values.
 *  (3) Loading state while compare call is in flight.
 *  (4) Error state when the API call fails.
 */

// --- Module mocks (hoisted before imports) -----------------------------------

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/api", () => ({
  listHouseholds: jest.fn(),
  getHousehold: jest.fn(),
  compareScenarios: jest.fn(),
  listScenarioPolicies: jest.fn(),
}));

jest.mock("next/link", () => {
  const MockLink = ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>;
  MockLink.displayName = "MockLink";
  return MockLink;
});

// --- Imports -----------------------------------------------------------------

import React from "react";
import "@testing-library/jest-dom";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { useRouter } from "next/navigation";
import {
  listHouseholds,
  getHousehold,
  compareScenarios,
  listScenarioPolicies,
} from "@/lib/api";
import ComparePage from "@/app/compare/page";

// --- Browser-API polyfills ---------------------------------------------------

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

// --- Fixtures ----------------------------------------------------------------

const mockHouseholds = [
  {
    household_id: "hh-001",
    filing_status: "joint",
    state: "CA",
    created_at: "2026-01-15T10:00:00Z",
  },
];

const mockHouseholdDetail = {
  household_id: "hh-001",
  household: {
    filing_status: "joint",
    self_birth_date: "1958-03-15",
    spouse_birth_date: "1960-03-15",
    state: "CA",
  },
  accounts: [],
  income: [],
  settings: {
    required_spending: 90_000,
    inflation: 0.03,
    nominal_return: 0.06,
    ss_pia_self: 2_400,
    ss_claim_age_self: 67,
    ss_pia_spouse: 2_000,
    ss_claim_age_spouse: 66,
    heir_tax_rate: 0.25,
    estate_weight: 1,
  },
  constraints: {},
};

const mockCompareResult = {
  result_a: {
    status: "ok",
    winning_policy: {
      policy_id: "fill_22",
      lifetime_taxes_nominal: 450_000,
      lifetime_taxes_pv: 380_000,
      terminal_estate: 1_200_000,
      success_probability: 0.9,
      score: 0.85,
      total_conversions: 300_000,
      projected_future_marginal_rate: 0.24,
    },
    yearly_plan: [
      {
        year: 2026,
        age_self: 68,
        balance_taxable: 300_000,
        balance_traditional: 750_000,
        balance_roth: 120_000,
        total_tax: 15_000,
      },
    ],
    alternative_policies: [],
    warnings: [],
    computation_time_seconds: 0.5,
    paths_evaluated: 10,
    monte_carlo_runs: 10,
  },
  result_b: {
    status: "ok",
    winning_policy: {
      policy_id: "fill_10",
      lifetime_taxes_nominal: 520_000,
      lifetime_taxes_pv: 430_000,
      terminal_estate: 1_050_000,
      success_probability: 0.82,
      score: 0.78,
      total_conversions: 50_000,
      projected_future_marginal_rate: 0.28,
    },
    yearly_plan: [
      {
        year: 2026,
        age_self: 68,
        balance_taxable: 290_000,
        balance_traditional: 760_000,
        balance_roth: 105_000,
        total_tax: 18_000,
      },
    ],
    alternative_policies: [],
    warnings: [],
    computation_time_seconds: 0.4,
    paths_evaluated: 10,
    monte_carlo_runs: 10,
  },
  difference: {
    lifetime_taxes_delta: -70_000,
    terminal_estate_delta: 150_000,
    success_probability_delta: 0.08,
    breakeven_year: 2031,
  },
};

// --- Helpers -----------------------------------------------------------------

const mockPush = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  (listHouseholds as jest.Mock).mockResolvedValue(mockHouseholds);
  (getHousehold as jest.Mock).mockResolvedValue(mockHouseholdDetail);
  (listScenarioPolicies as jest.Mock).mockResolvedValue({ policies: [] });
});

// --- Tests -------------------------------------------------------------------

describe("ComparePage — initial render", () => {
  it("renders the page heading", async () => {
    await act(async () => {
      render(<ComparePage />);
    });

    expect(
      screen.getByRole("heading", { name: /what-if analysis/i })
    ).toBeInTheDocument();
  });

  it("renders a Compare button", async () => {
    await act(async () => {
      render(<ComparePage />);
    });

    expect(
      screen.getByRole("button", { name: /compare/i })
    ).toBeInTheDocument();
  });

  it("labels the sides Baseline and Your changes", async () => {
    await act(async () => {
      render(<ComparePage />);
    });

    expect(screen.getByText("Baseline")).toBeInTheDocument();
    expect(screen.getByText("Your changes")).toBeInTheDocument();
  });
});

describe("ComparePage — scenario knobs", () => {
  it("renders spending, claim-age, and strategy knobs prefilled from the household", async () => {
    await act(async () => {
      render(<ComparePage />);
    });

    await waitFor(() => {
      expect(getHousehold).toHaveBeenCalledWith("hh-001");
    });

    // One of each knob per scenario form
    expect(screen.getAllByLabelText(/annual spending/i)).toHaveLength(2);
    expect(screen.getAllByLabelText(/your claim age/i)).toHaveLength(2);
    expect(screen.getAllByLabelText(/spouse claim age/i)).toHaveLength(2);
    // The retired optimization priority is no longer offered.
    expect(screen.queryAllByLabelText(/optimization priority/i)).toHaveLength(0);
    expect(screen.getAllByLabelText(/strategy/i)).toHaveLength(2);

    // Spending prefilled with the household's stored value
    const spendingInputs = screen.getAllByLabelText(
      /annual spending/i
    ) as HTMLInputElement[];
    // Formatted as the wizard formats currency.
    expect(spendingInputs[0].value).toBe("90,000");
    expect(spendingInputs[1].value).toBe("90,000");
  });

  // The widow's-penalty what-if. It lives HERE and not in the wizard on
  // purpose: modelling a death needs a year, and that guess belongs in a
  // comparison the user asked for, not inside their plan of record.
  it("offers the death what-if, defaulting to both alive", async () => {
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => {
      expect(getHousehold).toHaveBeenCalled();
    });

    const controls = screen.getAllByLabelText(/model first death at age/i);
    expect(controls).toHaveLength(2);
    expect(controls[0]).toHaveTextContent(/both alive throughout/i);
    // "Who dies first" only matters once a death is being modelled.
    expect(screen.queryByLabelText(/who dies first/i)).toBeNull();
  });

  it("sends the prefilled overrides on Compare", async () => {
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => {
      expect(getHousehold).toHaveBeenCalled();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });

    await waitFor(() => {
      expect(compareScenarios).toHaveBeenCalled();
    });
    const [hhId, , , overridesA, overridesB] = (compareScenarios as jest.Mock)
      .mock.calls[0];
    expect(hhId).toBe("hh-001");
    expect(overridesA).not.toHaveProperty("estate_weight");
    expect(overridesA).toMatchObject({
      required_spending: 90_000,
      ss_claim_age_self: 67,
      ss_claim_age_spouse: 66,
    });
    expect(overridesB).toMatchObject({
      required_spending: 90_000,
      ss_claim_age_self: 67,
      ss_claim_age_spouse: 66,
    });
  });

  it("sends an edited spending override for scenario A only", async () => {
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => {
      expect(getHousehold).toHaveBeenCalled();
    });

    const spendingInputs = screen.getAllByLabelText(/annual spending/i);
    fireEvent.change(spendingInputs[0], { target: { value: "150000" } });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });

    await waitFor(() => {
      expect(compareScenarios).toHaveBeenCalled();
    });
    const [, , , overridesA, overridesB] = (compareScenarios as jest.Mock).mock
      .calls[0];
    expect(overridesA.required_spending).toBe(150_000);
    expect(overridesB.required_spending).toBe(90_000);
  });

  it("highlights a changed field and states what the comparison tests", async () => {
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());
    expect(screen.getByTestId("changes-summary")).toHaveTextContent("Both sides match");

    const spending = screen.getAllByLabelText(/annual spending/i)[1];
    fireEvent.change(spending, { target: { value: "80000" } });

    const wrapper = spending.closest("[data-changed]");
    expect(wrapper).toHaveAttribute("data-changed", "true");
    expect(wrapper).toHaveTextContent("changed");
    // The baseline side is untouched.
    expect(screen.getAllByLabelText(/annual spending/i)[0].closest("[data-changed]")).toBeNull();
    expect(screen.getByTestId("changes-summary")).toHaveTextContent(
      "Comparing: Annual spending $90,000 → $80,000");
  });

  it("keeps advanced options collapsed", async () => {
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());
    expect(screen.getByTestId("b-advanced")).not.toHaveAttribute("open");
  });

  it("shows each scenario's winning policy after comparing", async () => {
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });

    await waitFor(() => {
      // result_a winner fill_22, result_b winner fill_10
      expect(screen.getByText(/fill the 22% bracket/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/fill the 10% bracket/i)).toBeInTheDocument();
  });
});

describe("ComparePage — scenario A is the stored plan", () => {
  // REGRESSION: the compare endpoint builds Constraints ENTIRELY from this
  // payload (constraints_from_model) and never reads the stored ones. So
  // leaving the constraint knobs at their defaults did not merely fail to
  // DISPLAY the plan's values — it replaced them. A plan capped at the 12%
  // conversion bracket was compared with no cap at all, on both sides, so
  // neither column was the user's plan.
  //
  // The old fixture had `constraints: {}`, which is why the whole suite passed
  // while this was broken.
  const planWithConstraints = {
    ...mockHouseholdDetail,
    settings: {
      ...mockHouseholdDetail.settings,
      spending_rule: "guardrails",
      spending_floor: 120_000,
    },
    constraints: {
      irmaa_policy: "avoid",
      conversion_window: "pre_rmd",
      marginal_rate_limit: 0.12,
      max_conversion_per_year: 50_000,
      preserve_taxable: true,
    },
  };

  it("prefills a 10% bracket cap on both sides", async () => {
    // REGRESSION: the dropdown had no 10% option, so a plan capped at 10%
    // showed a blank cap on Scenario A and B alike.
    (getHousehold as jest.Mock).mockResolvedValue({
      ...planWithConstraints,
      constraints: { ...planWithConstraints.constraints, marginal_rate_limit: "0.1" },
    });

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());

    await waitFor(() => {
      expect(screen.getByLabelText("Max ordinary-income bracket", { selector: "#a-maxbracket" }))
        .toHaveTextContent("10% bracket");
      expect(screen.getByLabelText("Max ordinary-income bracket", { selector: "#b-maxbracket" }))
        .toHaveTextContent("10% bracket");
    });
  });

  it("sends the plan's own constraints, not the page defaults", async () => {
    (getHousehold as jest.Mock).mockResolvedValue(planWithConstraints);
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });
    await waitFor(() => expect(compareScenarios).toHaveBeenCalled());

    const [, constraintsA, constraintsB] = (compareScenarios as jest.Mock)
      .mock.calls[0];

    // The knob that was actually being dropped.
    expect(constraintsA.marginal_rate_limit).toBe(0.12);
    expect(constraintsA).toMatchObject({
      irmaa_policy: "avoid",
      conversion_window: "pre_rmd",
      max_conversion_per_year: 50_000,
      preserve_taxable: true,
    });

    // Both sides start identical. B used to open on conversion_window
    // "pre_rmd" regardless of the plan — a difference the user never chose.
    expect(constraintsB).toEqual(constraintsA);
  });

  it("carries the plan's spending rule into both scenarios", async () => {
    (getHousehold as jest.Mock).mockResolvedValue(planWithConstraints);
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());

    // Visible on screen, not just in the payload — inheriting it invisibly
    // meant a guardrails plan and a fixed plan looked identical here.
    const rules = screen.getAllByLabelText(/if markets go badly/i);
    expect(rules).toHaveLength(2);
    expect(rules[0]).toHaveTextContent(/cut back, then recover/i);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });
    await waitFor(() => expect(compareScenarios).toHaveBeenCalled());

    const [, , , overridesA] = (compareScenarios as jest.Mock).mock.calls[0];
    expect(overridesA).toMatchObject({
      spending_rule: "guardrails",
      spending_floor: 120_000,
    });
  });
});

describe("ComparePage — year-by-year table", () => {
  // Two strategies can reach near-identical totals on opposite schedules —
  // front-loading at 24% vs waiting for the 10-12% years. The delta cards and
  // the chart both hide that; only the rows show it.
  const withConversions = {
    ...mockCompareResult,
    result_a: {
      ...mockCompareResult.result_a,
      yearly_plan: [
        { year: 2026, age_self: 68, conversion: 273_750, total_tax: 90_000,
          balance_taxable: 300_000, balance_traditional: 750_000, balance_roth: 120_000 },
        { year: 2027, age_self: 69, conversion: 0, total_tax: 20_000,
          balance_taxable: 280_000, balance_traditional: 700_000, balance_roth: 400_000 },
      ],
    },
    result_b: {
      ...mockCompareResult.result_b,
      yearly_plan: [
        { year: 2026, age_self: 68, conversion: 0, total_tax: 15_000,
          balance_taxable: 310_000, balance_traditional: 760_000, balance_roth: 120_000 },
        { year: 2027, age_self: 69, conversion: 123_000, total_tax: 40_000,
          balance_taxable: 300_000, balance_traditional: 640_000, balance_roth: 250_000 },
      ],
    },
  };

  async function renderWith(res: unknown) {
    (compareScenarios as jest.Mock).mockResolvedValue(res);
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });
  }

  it("shows each year's conversions for both scenarios", async () => {
    await renderWith(withConversions);
    const table = await screen.findByTestId("year-by-year");
    expect(table).toHaveTextContent("2026");
    expect(table).toHaveTextContent("$273,750");
    expect(table).toHaveTextContent("$123,000");
  });

  it("totals the conversions per scenario", async () => {
    await renderWith(withConversions);
    const table = await screen.findByTestId("year-by-year");
    expect(table).toHaveTextContent("Total conversions");
    // Not NaN — the guard against runs missing a field.
    expect(table).not.toHaveTextContent("NaN");
  });

  it("does not produce NaN when a stored run omits a field", async () => {
    // mockCompareResult's rows have no `conversion` key at all.
    await renderWith(mockCompareResult);
    const table = await screen.findByTestId("year-by-year");
    expect(table).not.toHaveTextContent("NaN");
  });

  it("can expand to every year", async () => {
    await renderWith(withConversions);
    const btn = await screen.findByRole("button", { name: /show all years/i });
    fireEvent.click(btn);
    expect(
      screen.getByRole("button", { name: /conversion years only/i }),
    ).toBeInTheDocument();
  });
});

describe("ComparePage — strategy menu matches the inputs", () => {
  // REGRESSION: the Strategy dropdown listed every policy label regardless of
  // the household. Picking "Fill the 12% bracket (greedy)" on a household whose
  // salary already exceeds the 12% bracket produced an HTTP 400 after clicking
  // Compare — the greedy fill_12 is never generated, only fill_12_annual is.
  // And the list is per SCENARIO: one listed for the stored plan offered a
  // scenario that closed the conversion window strategies it could not run.
  it("asks the backend which strategies each scenario's inputs allow", async () => {
    (listScenarioPolicies as jest.Mock).mockResolvedValue({
      policies: ["defer_1yr", "fill_10_annual", "fill_12_annual", "none"],
    });
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(listScenarioPolicies).toHaveBeenCalledTimes(2));
    const [hh, constraints, overrides] = (listScenarioPolicies as jest.Mock).mock.calls[0];
    expect(hh).toBe("hh-001");
    expect(constraints).toMatchObject({ irmaa_policy: "soft" });
    expect(overrides).toMatchObject({ required_spending: 90_000 });
    expect(overrides).not.toHaveProperty("policy_id");
  });

  it("keeps the page usable when that lookup fails", async () => {
    (listScenarioPolicies as jest.Mock).mockRejectedValue(new Error("offline"));
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(listScenarioPolicies).toHaveBeenCalled());
    // Still renders; a best-effort call must not break the form.
    expect(screen.getAllByLabelText(/strategy/i)).toHaveLength(2);
  });
});

describe("ComparePage — inputs must match the selected household", () => {
  it("keeps Compare disabled until the household's settings have loaded", async () => {
    let resolve: (v: unknown) => void = () => {};
    (getHousehold as jest.Mock).mockReturnValue(new Promise((r) => (resolve = r)));
    await act(async () => {
      render(<ComparePage />);
    });
    const button = screen.getByRole("button", { name: /^compare/i });
    // Comparing now would send the page defaults as this plan's constraints.
    expect(button).toBeDisabled();
    await act(async () => {
      resolve(mockHouseholdDetail);
    });
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("says so, and stays disabled, when the settings cannot be loaded", async () => {
    (getHousehold as jest.Mock).mockRejectedValue(new Error("offline"));
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() =>
      expect(screen.getByText(/couldn.t load this plan.s settings/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /^compare/i })).toBeDisabled();
  });
});

describe("ComparePage — clearing a stored spending floor", () => {
  it("sends an explicit null, which clears it, rather than omitting it", async () => {
    (getHousehold as jest.Mock).mockResolvedValue({
      ...mockHouseholdDetail,
      settings: {
        ...mockHouseholdDetail.settings,
        spending_rule: "guardrails",
        spending_floor: 120_000,
      },
    });
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);
    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() =>
      expect(screen.getAllByLabelText(/essential spending floor/i)).toHaveLength(2)
    );
    fireEvent.change(screen.getAllByLabelText(/essential spending floor/i)[0], {
      target: { value: "" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });
    await waitFor(() => expect(compareScenarios).toHaveBeenCalled());
    const [, , , overridesA, overridesB] = (compareScenarios as jest.Mock).mock.calls[0];
    expect(overridesA.spending_floor).toBeNull();
    expect(overridesB.spending_floor).toBe(120_000);
  });
});

describe("ComparePage — deterministic mode", () => {
  it("sends monte_carlo_runs: 0 when the simulation is skipped", async () => {
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("deterministic-toggle"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });
    await waitFor(() => expect(compareScenarios).toHaveBeenCalled());

    const call = (compareScenarios as jest.Mock).mock.calls[0];
    expect(call[5]).toBe(0);
  });

  it("leaves the run count to the default when the box is unchecked", async () => {
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });
    await waitFor(() => expect(compareScenarios).toHaveBeenCalled());

    expect((compareScenarios as jest.Mock).mock.calls[0][5]).toBeUndefined();
  });

  // With one return path success is 100% or 0%; a delta of those is noise
  // dressed as a measurement.
  it("hides the success-probability card on a deterministic result", async () => {
    const det = {
      ...mockCompareResult,
      result_a: { ...mockCompareResult.result_a, monte_carlo_runs: 0 },
      result_b: { ...mockCompareResult.result_b, monte_carlo_runs: 0 },
    };
    (compareScenarios as jest.Mock).mockResolvedValue(det);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });

    await waitFor(() =>
      expect(screen.queryByText(/Success Probability/i)).not.toBeInTheDocument(),
    );
    // The economic cards are still there — only the meaningless one is gone.
    expect(screen.getByText(/Lifetime Taxes/i)).toBeInTheDocument();
  });

  it("keeps the success card on a simulated result", async () => {
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });
    await waitFor(() => expect(getHousehold).toHaveBeenCalled());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^compare/i }));
    });

    expect(await screen.findByText(/Success Probability/i)).toBeInTheDocument();
  });
});

describe("ComparePage — compare call and delta cards", () => {
  it("shows delta cards after a successful compare call", async () => {
    (compareScenarios as jest.Mock).mockResolvedValue(mockCompareResult);

    await act(async () => {
      render(<ComparePage />);
    });

    // Select a household (the selector should be populated)
    await waitFor(() => {
      expect(listHouseholds).toHaveBeenCalled();
    });

    // Click Compare
    const compareBtn = screen.getByRole("button", { name: /compare/i });
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    // Delta cards should appear
    await waitFor(() => {
      expect(compareScenarios).toHaveBeenCalled();
    });

    // Lifetime taxes delta card
    await waitFor(() => {
      expect(screen.getByText(/lifetime taxes/i)).toBeInTheDocument();
    });

    // Terminal estate delta card
    expect(screen.getByText(/terminal estate/i)).toBeInTheDocument();

    // Success probability delta card
    expect(screen.getByText(/success probability/i)).toBeInTheDocument();

    // Each card says who comes out ahead, in words — no A−B sign rule.
    expect(screen.getByText("Baseline: $70,000 less tax")).toBeInTheDocument();
    expect(screen.getByText("Baseline: $150,000 larger estate")).toBeInTheDocument();
    expect(
      screen.getByText("Baseline: 8.0 pts more likely to succeed")
    ).toBeInTheDocument();
    expect(screen.queryByText(/A−B|A\u2212B/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Negative = /)).not.toBeInTheDocument();
  });

  it("shows error message when compare fails", async () => {
    (compareScenarios as jest.Mock).mockRejectedValue(
      new Error("HTTP 404: household not found")
    );

    await act(async () => {
      render(<ComparePage />);
    });

    const compareBtn = screen.getByRole("button", { name: /compare/i });
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    await waitFor(() => {
      expect(
        screen.getByText(/household not found/i)
      ).toBeInTheDocument();
    });
  });
});
