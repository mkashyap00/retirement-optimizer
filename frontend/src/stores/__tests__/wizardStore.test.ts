/**
 * TDD tests for wizardStore — written BEFORE implementation.
 * Run: npm test -- --testPathPattern=wizardStore
 */

import { useWizardStore } from "../wizardStore";
import type { HouseholdDetail } from "@/lib/types";

/** A stored plan as it can come back from the API — older plans miss fields
 *  the current types require. loadFrom must cope, so these fixtures are
 *  deliberately partial; the cast states that rather than padding them out. */
function storedPlan(detail: unknown): HouseholdDetail {
  return detail as HouseholdDetail;
}

// Zustand stores can be tested by accessing state directly
function getStore() {
  return useWizardStore.getState();
}

beforeEach(() => {
  // Reset to defaults before each test
  useWizardStore.getState().reset();
});

// ---------------------------------------------------------------------------
// Default state
// ---------------------------------------------------------------------------

describe("default state", () => {
  it("starts at step 0", () => {
    expect(getStore().step).toBe(0);
  });

  it("has filing_status joint", () => {
    expect(getStore().data.household.filing_status).toBe("joint");
  });

  it("has state CA", () => {
    expect(getStore().data.household.state).toBe("CA");
  });

  it("has one starter account row", () => {
    const accounts = getStore().data.accounts;
    expect(accounts).toHaveLength(1);
    expect(accounts[0]).toEqual({
      account_type: "taxable",
      owner: "self",
      balance: 0,
      basis: 0,
    });
  });

  it("has empty income array", () => {
    expect(getStore().data.income).toHaveLength(0);
  });

  it("has required_spending 90000", () => {
    expect(getStore().data.settings.required_spending).toBe(90000);
  });

  it("has inflation 0.03", () => {
    expect(getStore().data.settings.inflation).toBe(0.03);
  });

  it("has nominal_return 0.06", () => {
    expect(getStore().data.settings.nominal_return).toBe(0.06);
  });

  it("has irmaa_policy soft", () => {
    expect(getStore().data.constraints.irmaa_policy).toBe("soft");
  });

  it("has conversion_window anytime", () => {
    expect(getStore().data.constraints.conversion_window).toBe("anytime");
  });

  it("has preserve_taxable false", () => {
    expect(getStore().data.constraints.preserve_taxable).toBe(false);
  });

  it("has nickname empty string by default", () => {
    expect(getStore().data.household.nickname).toBe("");
  });
});

// ---------------------------------------------------------------------------
// setField — top-level nested paths
// ---------------------------------------------------------------------------

describe("setField — household paths", () => {
  it("updates household.filing_status", () => {
    getStore().setField("household.filing_status", "single");
    expect(getStore().data.household.filing_status).toBe("single");
  });

  it("updates household.state", () => {
    getStore().setField("household.state", "TX");
    expect(getStore().data.household.state).toBe("TX");
  });

  it("updates household.self_birth_date", () => {
    getStore().setField("household.self_birth_date", "1965-06-15");
    expect(getStore().data.household.self_birth_date).toBe("1965-06-15");
  });

  it("does not clobber other household fields when setting one", () => {
    getStore().setField("household.state", "NY");
    expect(getStore().data.household.filing_status).toBe("joint");
  });
});

describe("setField — settings paths", () => {
  it("updates settings.required_spending", () => {
    getStore().setField("settings.required_spending", 120000);
    expect(getStore().data.settings.required_spending).toBe(120000);
  });

  it("updates settings.inflation", () => {
    getStore().setField("settings.inflation", 0.04);
    expect(getStore().data.settings.inflation).toBeCloseTo(0.04);
  });
});

describe("setField — constraints paths", () => {
  it("updates constraints.irmaa_policy", () => {
    getStore().setField("constraints.irmaa_policy", "strict");
    expect(getStore().data.constraints.irmaa_policy).toBe("strict");
  });

  it("updates constraints.preserve_taxable", () => {
    getStore().setField("constraints.preserve_taxable", true);
    expect(getStore().data.constraints.preserve_taxable).toBe(true);
  });
});

describe("setField — accounts array index paths", () => {
  it("updates accounts.0.balance", () => {
    getStore().setField("accounts.0.balance", 50000);
    expect(getStore().data.accounts[0].balance).toBe(50000);
  });

  it("updates accounts.0.account_type", () => {
    getStore().setField("accounts.0.account_type", "roth");
    expect(getStore().data.accounts[0].account_type).toBe("roth");
  });

  it("updates accounts.0.owner", () => {
    getStore().setField("accounts.0.owner", "spouse");
    expect(getStore().data.accounts[0].owner).toBe("spouse");
  });

  it("does not clobber other account fields when setting one", () => {
    getStore().setField("accounts.0.balance", 99999);
    expect(getStore().data.accounts[0].account_type).toBe("taxable");
  });

  it("updates a second account by index", () => {
    getStore().addAccount();
    getStore().setField("accounts.1.balance", 75000);
    expect(getStore().data.accounts[1].balance).toBe(75000);
    expect(getStore().data.accounts[0].balance).toBe(0);
  });
});

describe("setField — income array index paths", () => {
  it("updates income.0.amount after addIncome", () => {
    getStore().addIncome();
    getStore().setField("income.0.amount", 55000);
    expect(getStore().data.income[0].amount).toBe(55000);
  });
});

// ---------------------------------------------------------------------------
// next / back — clamping
// ---------------------------------------------------------------------------

describe("next and back", () => {
  it("next increments step", () => {
    getStore().next();
    expect(getStore().step).toBe(1);
  });

  it("back decrements step", () => {
    getStore().next();
    getStore().back();
    expect(getStore().step).toBe(0);
  });

  it("back does not go below 0", () => {
    getStore().back();
    expect(getStore().step).toBe(0);
  });

  it("next does not exceed 5 (Review and run)", () => {
    for (let i = 0; i < 10; i++) getStore().next();
    expect(getStore().step).toBe(5);
  });

  it("next at step 3 goes to 4", () => {
    for (let i = 0; i < 3; i++) getStore().next();
    expect(getStore().step).toBe(3);
    getStore().next();
    expect(getStore().step).toBe(4);
  });
});

// ---------------------------------------------------------------------------
// addAccount / removeAccount
// ---------------------------------------------------------------------------

describe("addAccount", () => {
  it("appends a starter account row", () => {
    getStore().addAccount();
    expect(getStore().data.accounts).toHaveLength(2);
  });

  it("appended row has correct defaults", () => {
    getStore().addAccount();
    expect(getStore().data.accounts[1]).toEqual({
      account_type: "taxable",
      owner: "self",
      balance: 0,
      basis: 0,
    });
  });

  it("existing accounts are not mutated when adding", () => {
    getStore().setField("accounts.0.balance", 12345);
    getStore().addAccount();
    expect(getStore().data.accounts[0].balance).toBe(12345);
  });
});

describe("removeAccount", () => {
  it("removes account at index 0", () => {
    getStore().addAccount();
    getStore().setField("accounts.1.balance", 99);
    getStore().removeAccount(0);
    expect(getStore().data.accounts).toHaveLength(1);
    expect(getStore().data.accounts[0].balance).toBe(99);
  });

  it("removes account at index 1", () => {
    getStore().addAccount();
    getStore().setField("accounts.0.balance", 111);
    getStore().setField("accounts.1.balance", 222);
    getStore().removeAccount(1);
    expect(getStore().data.accounts).toHaveLength(1);
    expect(getStore().data.accounts[0].balance).toBe(111);
  });

  it("handles removing the only account", () => {
    getStore().removeAccount(0);
    expect(getStore().data.accounts).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// addIncome / removeIncome
// ---------------------------------------------------------------------------

describe("addIncome", () => {
  it("appends an income row", () => {
    getStore().addIncome();
    expect(getStore().data.income).toHaveLength(1);
  });

  it("appended income row has correct defaults", () => {
    getStore().addIncome();
    expect(getStore().data.income[0]).toEqual({
      category: "salary",
      owner: "self",
      amount: 0,
    });
  });
});

describe("removeIncome", () => {
  it("removes income row at index", () => {
    getStore().addIncome();
    getStore().addIncome();
    getStore().setField("income.1.amount", 60000);
    getStore().removeIncome(0);
    expect(getStore().data.income).toHaveLength(1);
    expect(getStore().data.income[0].amount).toBe(60000);
  });
});

// ---------------------------------------------------------------------------
// reset
// ---------------------------------------------------------------------------

describe("reset", () => {
  it("restores step to 0", () => {
    getStore().next();
    getStore().next();
    getStore().reset();
    expect(getStore().step).toBe(0);
  });

  it("restores defaults after mutations", () => {
    getStore().setField("household.state", "TX");
    getStore().setField("settings.required_spending", 200000);
    getStore().addAccount();
    getStore().reset();

    const data = getStore().data;
    expect(data.household.state).toBe("CA");
    expect(data.settings.required_spending).toBe(90000);
    expect(data.accounts).toHaveLength(1);
  });

  it("reset accounts back to one starter row", () => {
    getStore().addAccount();
    getStore().addAccount();
    getStore().reset();
    expect(getStore().data.accounts).toHaveLength(1);
    expect(getStore().data.accounts[0]).toEqual({
      account_type: "taxable",
      owner: "self",
      balance: 0,
      basis: 0,
    });
  });
});

// ---------------------------------------------------------------------------
// loadFrom — DB nulls must not poison the store (silent Review-block bug)
// ---------------------------------------------------------------------------

describe("loadFrom null handling", () => {
  it("strips DB nulls so defaults backfill and zod validation passes", () => {
    useWizardStore.getState().loadFrom(storedPlan({
      household_id: "hh-x",
      household: {
        filing_status: "joint",
        self_birth_date: "1962-12-19",
        spouse_birth_date: "1966-12-24",
        state: "CA",
        nickname: "First",
        self_death_age: null,
        spouse_death_age: null,
      },
      accounts: [
        // traditional with DB-null basis — must not become basis: null
        { account_type: "traditional", owner: "self", balance: 500000, basis: null as unknown as undefined },
      ],
      income: [
        { category: "qualified_dividend", owner: "spouse", amount: 45000,
          start_year: null as unknown as undefined, end_year: null as unknown as undefined },
      ],
      settings: {
        required_spending: 120000,
        inflation: 0.03,
        nominal_return: 0.06,
        ss_pia_self: 3500,
        ss_claim_age_self: 67,
        ss_pia_spouse: 2000,
        // The poison value from the user's real plan:
        ss_claim_age_spouse: null as unknown as undefined,
      },
      constraints: {},
    }));

    const d = useWizardStore.getState().data;
    // Nulls stripped → undefined (or default), never null
    expect(d.accounts[0].basis).not.toBeNull();
    expect(d.income[0].start_year).not.toBeNull();
    // Real values preserved
    expect(d.settings.required_spending).toBe(120000);
    expect(d.settings.ss_pia_spouse).toBe(2000);
    // "No age chosen" stays unchosen -- not replaced by an invented 67.
    expect(d.settings.ss_claim_age_spouse).toBeNull();
    expect(d.settings.ss_claim_age_self).toBe(67);
  });

  it("spells out a blank plan-through age as the projection it had", () => {
    const year = new Date().getFullYear();
    useWizardStore.getState().loadFrom(storedPlan({
      household_id: "hh-y",
      household: {
        filing_status: "joint", self_birth_date: "1962-12-19", spouse_birth_date: "1966-12-24",
        state: "CA", self_death_age: null, spouse_death_age: null,
      },
      accounts: [], income: [],
      settings: { required_spending: 1, inflation: 0.03, nominal_return: 0.06, ss_pia_self: 0,
                  ss_claim_age_self: 67 },
      constraints: {},
    }));
    const h = useWizardStore.getState().data.household;
    // Both blank projected 30 years: through year + 29 for each of them.
    expect(h.self_death_age).toBe(year + 29 - 1962);
    expect(h.spouse_death_age).toBe(year + 29 - 1966);
  });
});

// ---------------------------------------------------------------------------
// loadFrom — copied plans get a self-describing nickname
// ---------------------------------------------------------------------------

describe("loadFrom copy naming", () => {
  it("prefixes the copied nickname with 'Copy of'", () => {
    useWizardStore.getState().loadFrom(storedPlan({
      household_id: "hh-x",
      household: {
        filing_status: "single",
        self_birth_date: "1962-12-19",
        state: "CA",
        nickname: "Second",
      },
      accounts: [],
      income: [],
      settings: { required_spending: 120000, inflation: 0.03, nominal_return: 0.06, ss_pia_self: 3500 },
      constraints: {},
    }));
    expect(getStore().data.household.nickname).toBe("Copy of Second");
  });

  it("leaves the nickname empty when the source had none", () => {
    useWizardStore.getState().loadFrom(storedPlan({
      household_id: "hh-x",
      household: {
        filing_status: "single",
        self_birth_date: "1962-12-19",
        state: "CA",
      },
      accounts: [],
      income: [],
      settings: { required_spending: 120000, inflation: 0.03, nominal_return: 0.06, ss_pia_self: 3500 },
      constraints: {},
    }));
    expect(getStore().data.household.nickname).toBe("");
  });

  it("truncates 'Copy of' names to the 60-char nickname limit", () => {
    useWizardStore.getState().loadFrom(storedPlan({
      household_id: "hh-x",
      household: {
        filing_status: "single",
        self_birth_date: "1962-12-19",
        state: "CA",
        nickname: "x".repeat(60),
      },
      accounts: [],
      income: [],
      settings: { required_spending: 120000, inflation: 0.03, nominal_return: 0.06, ss_pia_self: 3500 },
      constraints: {},
    }));
    const nick = getStore().data.household.nickname as string;
    expect(nick.startsWith("Copy of xxx")).toBe(true);
    expect(nick.length).toBeLessThanOrEqual(60);
  });
});
