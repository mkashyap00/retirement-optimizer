/**
 * @jest-environment jsdom
 *
 * Persistence roundtrip tests for the wizard Zustand store.
 * Verifies that persisted data survives across rehydration.
 */

import { useWizardStore } from "../wizardStore";

beforeEach(() => {
  localStorage.clear();
  useWizardStore.getState().reset();
});

// ---------------------------------------------------------------------------
// Persistence roundtrip: set field → read from localStorage → rehydrate → value present
// ---------------------------------------------------------------------------

describe("Draft persistence roundtrip", () => {
  it("setField persists data to localStorage under the wizard-draft key", async () => {
    useWizardStore.getState().setField("household.nickname", "Persisted Plan");

    // Allow the persist middleware to write (it does so synchronously in this setup)
    const raw = localStorage.getItem("wizard-draft");
    expect(raw).not.toBeNull();

    const stored = JSON.parse(raw!);
    expect(stored.state.data.household.nickname).toBe("Persisted Plan");
  });

  it("rehydrate() restores state from localStorage", async () => {
    // Write a draft directly to localStorage
    const draftState = {
      state: {
        data: {
          household: {
            filing_status: "single",
            state: "TX",
            self_birth_date: "1960-01-15",
            spouse_birth_date: "",
            nickname: "Rehydrated Plan",
          },
          accounts: [
            {
              account_type: "taxable",
              owner: "self",
              balance: 250000,
              basis: 100000,
            },
          ],
          income: [],
          settings: {
            required_spending: 75000,
            inflation: 0.03,
            nominal_return: 0.06,
            ss_pia_self: 2200,
            ss_claim_age_self: 67,
          },
          constraints: {
            irmaa_policy: "soft",
            conversion_window: "anytime",
            preserve_taxable: false,
          },
        },
        step: 2,
        visitedMax: 2,
      },
      version: 0,
    };

    localStorage.setItem("wizard-draft", JSON.stringify(draftState));

    // Trigger rehydration
    await useWizardStore.persist.rehydrate();

    const state = useWizardStore.getState();
    expect(state.data.household.nickname).toBe("Rehydrated Plan");
    expect(state.data.household.state).toBe("TX");
    expect(state.step).toBe(2);
    expect(state.visitedMax).toBe(2);
  });

  it("clearDraft() removes draft and resets to defaults", () => {
    useWizardStore.getState().setField("household.nickname", "To Be Cleared");
    useWizardStore.getState().next();

    useWizardStore.getState().clearDraft();

    const state = useWizardStore.getState();
    expect(state.data.household.nickname).toBe("");
    expect(state.step).toBe(0);
    expect(state.visitedMax).toBe(0);
  });

  it("visitedMax is updated as steps are visited", () => {
    expect(useWizardStore.getState().visitedMax).toBe(0);

    useWizardStore.getState().next();
    expect(useWizardStore.getState().visitedMax).toBe(1);

    useWizardStore.getState().next();
    expect(useWizardStore.getState().visitedMax).toBe(2);

    // Going back does NOT reduce visitedMax
    useWizardStore.getState().back();
    expect(useWizardStore.getState().visitedMax).toBe(2);
  });

  it("goToStep only works for previously-visited steps", () => {
    // Start at step 0, visitedMax = 0
    useWizardStore.getState().goToStep(3); // not visited
    expect(useWizardStore.getState().step).toBe(0); // unchanged

    useWizardStore.getState().next(); // step=1, visitedMax=1
    useWizardStore.getState().next(); // step=2, visitedMax=2

    useWizardStore.getState().goToStep(0); // visited — allowed
    expect(useWizardStore.getState().step).toBe(0);

    useWizardStore.getState().goToStep(4); // not visited
    expect(useWizardStore.getState().step).toBe(0); // unchanged
  });

  it("deep-merge backfills missing constraint keys from defaults", async () => {
    // Seed localStorage with a partial draft (missing constraints)
    const partialDraft = {
      state: {
        data: {
          household: {
            filing_status: "single",
            state: "TX",
            self_birth_date: "1970-05-10",
            spouse_birth_date: "",
            nickname: "Partial",
          },
          accounts: [
            {
              account_type: "roth",
              owner: "self",
              balance: 100000,
              basis: 100000,
            },
          ],
          income: [
            {
              category: "other",
              owner: "self",
              amount: 25000,
            },
          ],
          settings: {
            required_spending: 80000,
            inflation: 0.025,
            nominal_return: 0.065,
            ss_pia_self: 1500,
            ss_claim_age_self: 70,
          },
          // Intentionally missing constraints — should be backfilled
        },
        step: 1,
        visitedMax: 1,
      },
      version: 1,
    };

    localStorage.setItem("wizard-draft", JSON.stringify(partialDraft));

    // Trigger rehydration
    await useWizardStore.persist.rehydrate();

    const state = useWizardStore.getState();

    // Verify stored data survives
    expect(state.data.household.state).toBe("TX");
    expect(state.data.household.nickname).toBe("Partial");
    expect(state.data.accounts[0].account_type).toBe("roth");
    expect(state.data.accounts[0].balance).toBe(100000);
    expect(state.data.income[0].amount).toBe(25000);
    expect(state.data.settings.required_spending).toBe(80000);
    expect(state.step).toBe(1);

    // Verify missing constraints are backfilled with defaults
    expect(state.data.constraints).toBeDefined();
    expect(state.data.constraints.irmaa_policy).toBe("soft");
    expect(state.data.constraints.conversion_window).toBe("anytime");
    expect(state.data.constraints.preserve_taxable).toBe(false);
  });
});
