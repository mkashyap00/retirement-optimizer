/**
 * @jest-environment jsdom
 */
import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { InputsPanel } from "../InputsPanel";
import type { HouseholdDetail } from "@/lib/types";

function inputs(settings: Partial<HouseholdDetail["settings"]>): HouseholdDetail {
  return {
    household_id: "hh-1",
    household: {
      filing_status: "joint",
      self_birth_date: "1964-01-01",
      spouse_birth_date: "1965-01-01",
      state: "CA",
    },
    accounts: [],
    income: [],
    settings: {
      required_spending: 90000,
      inflation: 0.03,
      nominal_return: 0.06,
      ss_pia_self: 3000,
      ss_claim_age_self: 67,
      ...settings,
    },
    constraints: { irmaa_policy: "soft", conversion_window: "anytime", preserve_taxable: false },
  } as HouseholdDetail;
}

function colaText(settings: Partial<HouseholdDetail["settings"]>): string {
  const { unmount } = render(<InputsPanel inputs={inputs(settings)} />);
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  const label = screen.getByText("Social Security COLA");
  const text = label.nextElementSibling?.textContent ?? "";
  unmount();
  return text;
}

describe("InputsPanel Social Security COLA row", () => {
  it("shows flat benefits for snapshots saved before the setting existed", () => {
    expect(colaText({})).toBe("None (benefits held flat)");
  });

  it("shows the inflation rate when the COLA follows inflation", () => {
    expect(colaText({ ss_cola: null })).toMatch(/Follows inflation \(3(\.0)?%\)/);
  });

  it("shows an explicit rate, and zero as flat", () => {
    expect(colaText({ ss_cola: 0.025 })).toMatch(/2\.5/);
    expect(colaText({ ss_cola: 0 })).toBe("None (benefits held flat)");
  });
});

describe("InputsPanel objective row", () => {
  function row(objective: string | undefined, estate_weight?: number) {
    const { unmount } = render(
      <InputsPanel inputs={inputs({ estate_weight })} objective={objective} />,
    );
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const label =
      screen.queryByText("Objective") ?? screen.getByText("Optimization priority");
    const out = [label.textContent, label.nextElementSibling?.textContent];
    unmount();
    return out;
  }

  it("names the objective on runs that carry one, whatever estate_weight says", () => {
    const [label, value] = row("pv_estate_minus_weighted_shortfall", 0);
    expect(label).toBe("Objective");
    expect(value).toMatch(/After-tax estate, less unfunded spending/);
  });

  it("keeps the stored priority on runs saved before the objective changed", () => {
    expect(row(undefined, 0)).toEqual(["Optimization priority", "Lifetime taxes"]);
    expect(row(undefined, undefined)).toEqual(["Optimization priority", "Estate"]);
  });
});

describe("taxTablesLabel", () => {
  it("describes frozen tables on older runs and projection on new ones", () => {
    const { taxTablesLabel } = jest.requireActual("../InputsPanel");
    expect(taxTablesLabel(undefined)).toBe("Frozen at the last published year");
    const label = taxTablesLabel({
      federal_published_through: 2026,
      irmaa_published_through: 2026,
      state_published_through: 2025,
      state_indexed: ["CA"],
      indexation_rate: 0.03,
      irmaa_premiums_projected: false,
    });
    expect(label).toContain("through 2026");
    expect(label).toContain("3.0%");
    expect(label).toContain("CA only");
  });
});

describe("InputsPanel claim ages and income years", () => {
  function body(settings: Partial<HouseholdDetail["settings"]>, claims?: Parameters<typeof InputsPanel>[0]["claims"]) {
    const data = inputs(settings);
    data.income = [{ category: "salary", owner: "self", amount: 100000, start_year: 2026, end_year: 2028 }];
    render(<InputsPanel inputs={data} claims={claims} />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    return screen.getByTestId("inputs-panel-body");
  }

  it("labels the PIA as the full-retirement-age benefit and shows income years", () => {
    const b = body({});
    expect(b).toHaveTextContent("Benefit at full retirement age (you)$3,000/mo");
    expect(b).toHaveTextContent("Salary (you)$100,000/yr · 2026–2028");
    expect(b).toHaveTextContent("Claim age (you)67 (entered)");
  });

  it("separates the entered age from the searched and recommended one", () => {
    const b = body({}, { joint: true, searched: { self: true }, used: { self: 69 } });
    expect(b).toHaveTextContent("Claim age (you)Entered 67 · searched · recommended 69");
  });

  it("says when a fixed-age run used another age, or the person already receives benefits", () => {
    expect(body({}, { joint: false, used: { self: 70 } })).toHaveTextContent("Entered 67 · this run used 70");
  });

  it("names someone already receiving", () => {
    expect(body({ ss_receiving_self: true, ss_claim_age_self: 63 })).toHaveTextContent(
      "Already receiving (claimed at 63)");
  });
});

describe("InputsPanel capital gains already realized", () => {
  it("lists the gains and carried-in loss the run used", () => {
    const data = inputs({});
    data.capital_gains = { tax_year: 2026, short_term: -4000, long_term: 25000,
      carryover_short_term: 1500, carryover_long_term: 0 };
    render(<InputsPanel inputs={data} />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const b = screen.getByTestId("inputs-panel-body");
    expect(b).toHaveTextContent("Gains realized in 2026 (− = loss)short-term −$4,000 · long-term $25,000");
    expect(b).toHaveTextContent("Loss carried into 2026short-term $1,500 · long-term $0");
  });
});
