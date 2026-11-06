import { capitalGainsLines, capitalGainsPayload, noCapitalGains } from "@/lib/capitalGains";
import { useWizardStore } from "@/stores/wizardStore";
import type { HouseholdDetail } from "@/lib/types";

const YEAR = new Date().getFullYear();

describe("capital gains already realized", () => {
  it("nothing entered saves nothing", () => {
    expect(capitalGainsPayload(noCapitalGains())).toBeNull();
    expect(capitalGainsPayload(null)).toBeNull();
    expect(capitalGainsLines(noCapitalGains())).toEqual([]);
  });

  it("a carried-over loss alone is still saved", () => {
    expect(capitalGainsPayload({ ...noCapitalGains(), carryover_short_term: 2000 })).toEqual({
      tax_year: YEAR, short_term: 0, long_term: 0,
      carryover_short_term: 2000, carryover_long_term: 0,
    });
  });

  it("describes losses with a minus sign", () => {
    const lines = capitalGainsLines({ ...noCapitalGains(), short_term: -4000, long_term: 25000 });
    expect(lines).toEqual([[`Gains realized in ${YEAR} (− = loss)`,
      "short-term −$4,000 · long-term $25,000"]]);
  });

  const detail = (taxYear: number): HouseholdDetail => ({
    household_id: "hh",
    household: { filing_status: "single", self_birth_date: "1960-01-01", state: "CA" },
    accounts: [],
    income: [],
    settings: {
      required_spending: 80000, inflation: 0.03, nominal_return: 0.06,
      ss_pia_self: 0, ss_claim_age_self: 67,
    },
    constraints: { irmaa_policy: "soft", conversion_window: "anytime", preserve_taxable: false },
    capital_gains: { tax_year: taxYear, short_term: 5000, long_term: 0,
      carryover_short_term: 0, carryover_long_term: 0 },
  });

  it("a copied plan keeps this year's gains", () => {
    useWizardStore.getState().loadFrom(detail(YEAR));
    expect(useWizardStore.getState().data.capital_gains?.short_term).toBe(5000);
  });

  it("a copied plan drops gains entered for an earlier year", () => {
    useWizardStore.getState().loadFrom(detail(YEAR - 1));
    expect(useWizardStore.getState().data.capital_gains).toEqual(noCapitalGains());
  });
});
