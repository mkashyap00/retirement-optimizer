import { validateStep } from "@/components/wizard/schemas";
import type { HouseholdPayload } from "@/lib/types";

function payload(over: Partial<HouseholdPayload> = {}): HouseholdPayload {
  return {
    household: {
      filing_status: "single",
      state: "CA",
      self_birth_date: "1960-01-01",
    },
    accounts: [
      { account_type: "taxable", owner: "self", balance: 30000, basis: 50000 },
    ],
    income: [],
    settings: {
      required_spending: 50000,
      inflation: 0.03,
      nominal_return: 0.06,
      ss_pia_self: 0,
      ss_claim_age_self: 67,
    },
    constraints: { irmaa_policy: "soft", conversion_window: "anytime" },
    ...over,
  } as HouseholdPayload;
}

const ACCOUNTS_STEP = 2;

describe("accounts step", () => {
  it("accepts a taxable account at a loss", () => {
    // Basis above market value is an ordinary unrealized loss.
    expect(validateStep(ACCOUNTS_STEP, payload()).success).toBe(true);
  });

  it("still rejects a traditional after-tax basis above the balance", () => {
    const p = payload({
      accounts: [
        { account_type: "traditional", owner: "self", balance: 1000, basis: 2000 },
      ],
    });
    const r = validateStep(ACCOUNTS_STEP, p);
    expect(r.success).toBe(false);
    expect(r.errors["accounts.0.basis"]).toBeDefined();
  });

  it("rejects a spouse-owned account when there is no spouse", () => {
    // Left over after switching from joint to single; the API rejects it.
    const p = payload({
      accounts: [{ account_type: "roth", owner: "spouse", balance: 1000 }],
    });
    const r = validateStep(ACCOUNTS_STEP, p);
    expect(r.success).toBe(false);
    expect(r.errors["accounts.0.owner"]).toMatch(/spouse/i);
  });

  it("requires the year opened for a Roth with a balance (5-year rule)", () => {
    const roth = (balance: number, year?: number | null) =>
      validateStep(ACCOUNTS_STEP, payload({
        accounts: [{ account_type: "roth", owner: "self", balance, roth_opened_year: year }],
      }));
    expect(roth(1000).errors["accounts.0.roth_opened_year"]).toMatch(/5-year rule/);
    expect(roth(1000, null).success).toBe(false);
    expect(roth(1000, 2020).success).toBe(true);
    expect(roth(0).success).toBe(true);
    expect(roth(1000, new Date().getFullYear() + 1).errors["accounts.0.roth_opened_year"])
      .toMatch(/future/);
  });
});

describe("Social Security step: claim age vs already receiving", () => {
  const SS_STEP = 3;
  const year = new Date().getFullYear();
  const withSS = (claim: number, receiving: boolean | null | undefined, age = 66) =>
    payload({
      household: { filing_status: "single", state: "CA", self_birth_date: `${year - age}-06-01` },
      settings: {
        required_spending: 50000, inflation: 0.03, nominal_return: 0.06,
        ss_pia_self: 2000, ss_claim_age_self: claim, ss_receiving_self: receiving,
      },
    } as Partial<HouseholdPayload>);

  it("accepts a plan to claim later and an actual earlier claim", () => {
    expect(validateStep(SS_STEP, withSS(67, false)).success).toBe(true);
    expect(validateStep(SS_STEP, withSS(66, false)).success).toBe(true); // files this year
    expect(validateStep(SS_STEP, withSS(63, true)).success).toBe(true);
  });

  it("rejects a planned age already passed, asking to confirm receiving", () => {
    const r = validateStep(SS_STEP, withSS(64, false));
    expect(r.success).toBe(false);
    expect(r.errors["ss_claim_age_self"]).toMatch(/already receiving/i);
  });

  it("rejects a claim already started at an age not yet reached", () => {
    const r = validateStep(SS_STEP, withSS(68, true));
    expect(r.errors["ss_claim_age_self"]).toMatch(/66 or earlier/);
  });

  it("over 70 and not receiving files now at 70", () => {
    expect(validateStep(SS_STEP, withSS(70, false, 73)).success).toBe(true);
    expect(validateStep(SS_STEP, withSS(69, false, 73)).success).toBe(false);
  });

  it("from 62 an unanswered flag must be answered, not assumed to be No", () => {
    const r = validateStep(SS_STEP, withSS(64, null));
    expect(r.success).toBe(false);
    expect(r.errors["ss_receiving_self"]).toMatch(/already receiving/);
  });

  it("under 62 the question is not asked", () => {
    expect(validateStep(SS_STEP, withSS(67, null, 60)).success).toBe(true);
  });
});
