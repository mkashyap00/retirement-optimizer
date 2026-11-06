/**
 * @jest-environment jsdom
 *
 * RTL tests for the six-step wizard and submit flow.
 * Updated for Phase B: progress rail, Zod validation, summary aside, framer-motion.
 */

// --- Module mocks (hoisted by Jest before imports) --------------------------

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/api", () => ({
  createHousehold: jest.fn(),
  optimize: jest.fn(),
  listHouseholds: jest.fn().mockResolvedValue([]),
  getHousehold: jest.fn(),
  getPortfolio: jest.fn(),
  previewClaimAges: jest.fn(),
  getActiveOptimizeJob: jest.fn(),
  submitOptimizeJob: jest.fn(),
  updateHousehold: jest.fn(),
}));

// Mock framer-motion so animations don't interfere with tests
jest.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
  motion: {
    div: ({
      children,
      className,
      ...rest
    }: {
      children?: React.ReactNode;
      className?: string;
      [key: string]: unknown;
    }) => (
      <div className={className} {...(rest as React.HTMLAttributes<HTMLDivElement>)}>
        {children}
      </div>
    ),
  },
  useReducedMotion: () => false,
}));

// --- Imports ----------------------------------------------------------------

import React from "react";
import type { Config } from "@jest/types";
import "@testing-library/jest-dom";
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
  within,
} from "@testing-library/react";
import { useRouter } from "next/navigation";
import {
  createHousehold,
  optimize,
  previewClaimAges,
  getActiveOptimizeJob,
  submitOptimizeJob,
  listHouseholds,
  getHousehold,
  getPortfolio,
  updateHousehold,
} from "@/lib/api";
import { savePlanModes } from "@/lib/planModes";
import { useWizardStore } from "@/stores/wizardStore";
import WizardPage from "@/app/wizard/page";
import {
  StepProfile,
  StepAccounts,
  StepSpendingGoals,
  StepReview,
  StepIncomeAndSS,
} from "@/components/wizard/steps";
import { validateStep } from "@/components/wizard/schemas";
import { ApiError } from "@/lib/apiError";

// --- Browser-API polyfills for jsdom ----------------------------------------

beforeAll(() => {
  Object.defineProperty(global, "ResizeObserver", {
    writable: true,
    value: jest.fn().mockImplementation(() => ({
      observe: jest.fn(),
      unobserve: jest.fn(),
      disconnect: jest.fn(),
    })),
  });

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
});

// --- Per-test setup ---------------------------------------------------------

const mockPush = jest.fn();

beforeEach(() => {
  useWizardStore.getState().reset();

  (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  mockPush.mockClear();

  (createHousehold as jest.Mock).mockResolvedValue({ household_id: "hh-1" });
  (optimize as jest.Mock).mockResolvedValue({ run_id: "run-1", result: {} });
  (createHousehold as jest.Mock).mockClear();
  (optimize as jest.Mock).mockClear();
  (createHousehold as jest.Mock).mockResolvedValue({ household_id: "hh-1" });
  (optimize as jest.Mock).mockResolvedValue({ run_id: "run-1", result: {} });

  // Both people searchable at 62–70; the tests that expect the plain
  // conversion optimizer hold both ages fixed (the search has its own test).
  const person = (entered: number) => ({
    status: "searchable", age: 60, entered_age: entered, receiving: false, pia: 2000,
    ages: [62, 63, 64, 65, 66, 67, 68, 69, 70], exclusions: [], message: null,
  });
  (previewClaimAges as jest.Mock).mockResolvedValue({ self: person(67), spouse: person(67) });
  (getActiveOptimizeJob as jest.Mock).mockResolvedValue(null);
  (submitOptimizeJob as jest.Mock).mockResolvedValue({ job_id: "job-1", status: "queued" });
  useWizardStore.getState().setClaimModes({ self: "fixed", spouse: "fixed" });
  // A new plan starts with no claim age; these tests hold 67 fixed.
  useWizardStore.getState().setField("settings.ss_claim_age_self", 67);
  useWizardStore.getState().setField("settings.ss_claim_age_spouse", 67);

  // Default: no portfolio uploaded → no autofill (existing tests unaffected).
  (getPortfolio as jest.Mock).mockResolvedValue({
    positions: [],
    uploaded_at: null,
    warnings: [],
  });
});

function portfolioWithTaxableBasis(costBasis: number) {
  return {
    positions: [
      {
        ticker: "VTI",
        account_type: "taxable",
        shares: 100,
        price: 300,
        market_value: 30000,
        cost_basis: costBasis,
        holding_period: "long_term" as const,
      },
    ],
    uploaded_at: "2026-07-23T00:00:00Z",
    warnings: [],
  };
}

// ---------------------------------------------------------------------------
// (a) Step 1 renders; selecting filing_status single hides spouse date
// ---------------------------------------------------------------------------

describe("StepProfile (step 1)", () => {
  it("renders the Household Profile title", () => {
    render(<StepProfile />);
    expect(screen.getByText("Household Profile")).toBeInTheDocument();
  });

  it("shows the Your Birth Date input", () => {
    render(<StepProfile />);
    expect(screen.getByLabelText(/Your Birth Date/i)).toBeInTheDocument();
  });

  it("shows Spouse Birth Date when filing_status is joint (default)", () => {
    render(<StepProfile />);
    expect(screen.getByLabelText(/Spouse Birth Date/i)).toBeInTheDocument();
  });

  it("shows the Plan nickname field in step 1", () => {
    render(<StepProfile />);
    expect(screen.getByLabelText(/Plan nickname/i)).toBeInTheDocument();
  });

  it("hides Spouse Birth Date when filing_status changes to single", () => {
    render(<StepProfile />);

    expect(screen.getByLabelText(/Spouse Birth Date/i)).toBeInTheDocument();

    act(() => {
      useWizardStore.getState().setField("household.filing_status", "single");
    });

    expect(
      screen.queryByLabelText(/Spouse Birth Date/i)
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (b) Next button advances to step 2 — requires valid step-1 data
// ---------------------------------------------------------------------------

/** Render the wizard and wait for the entry-phase check to settle.
 *
 *  The page holds a skeleton until listHouseholds() resolves — without that it
 *  rendered step 1 and swapped it out a moment later, which users saw as a
 *  flash when clicking New Plan. Tests therefore have to await the form.
 */
async function renderWizard() {
  const utils = render(<WizardPage />);
  await screen.findByRole("button", { name: /Next/i });
  return utils;
}

describe("WizardPage navigation", () => {
  it("clicking Next from step 0 (with valid data) renders step 1 (Planning Assumptions)", async () => {
    await renderWizard();

    // Provide valid step-1 data to pass Zod schema
    act(() => {
      useWizardStore.getState().setField("household.self_birth_date", "1965-06-15");
      useWizardStore.getState().setField("household.spouse_birth_date", "1967-03-20");
    });

    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    expect(screen.getByText("Planning Assumptions")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (c) Accounts step: Add Account adds a row
// ---------------------------------------------------------------------------

describe("StepAccounts (step 2)", () => {
  it("renders with one account row by default", () => {
    render(<StepAccounts />);
    expect(screen.getAllByRole("button", { name: /Remove/i })).toHaveLength(1);
  });

  it("clicking 'Add Account' appends a new account row", () => {
    render(<StepAccounts />);

    fireEvent.click(screen.getByRole("button", { name: /Add Account/i }));

    expect(screen.getAllByRole("button", { name: /Remove/i })).toHaveLength(2);
  });

  it("auto-fills taxable cost basis from an uploaded portfolio", async () => {
    (getPortfolio as jest.Mock).mockResolvedValue(
      portfolioWithTaxableBasis(812345)
    );
    render(<StepAccounts />);

    await waitFor(() =>
      expect(screen.getByTestId("basis-autofilled-0")).toBeInTheDocument()
    );
    // The store value IS the displayed value (rounded portfolio total).
    expect(useWizardStore.getState().data.accounts[0].basis).toBe(812345);
    expect(screen.getByTestId("basis-autofilled-0").textContent).toMatch(
      /\$812,345/
    );
  });

  it("does not clobber a cost basis the user already entered", async () => {
    act(() => {
      useWizardStore.getState().setField("accounts.0.basis", 500000);
    });
    (getPortfolio as jest.Mock).mockResolvedValue(
      portfolioWithTaxableBasis(812345)
    );
    render(<StepAccounts />);

    // Give the effect a chance to run, then confirm the typed value stands.
    await waitFor(() => expect(getPortfolio).toHaveBeenCalled());
    expect(useWizardStore.getState().data.accounts[0].basis).toBe(500000);
    expect(screen.queryByTestId("basis-autofilled-0")).not.toBeInTheDocument();
  });

  it("does not auto-fill when no portfolio is uploaded", async () => {
    // beforeEach default: empty positions.
    render(<StepAccounts />);
    await waitFor(() => expect(getPortfolio).toHaveBeenCalled());
    expect(useWizardStore.getState().data.accounts[0].basis).toBe(0);
    expect(screen.queryByTestId("basis-autofilled-0")).not.toBeInTheDocument();
  });

  it("skips auto-fill when there are multiple taxable accounts (ambiguous split)", async () => {
    act(() => {
      // Two taxable accounts → the split is ambiguous, so leave both.
      useWizardStore.getState().addAccount();
    });
    (getPortfolio as jest.Mock).mockResolvedValue(
      portfolioWithTaxableBasis(812345)
    );
    render(<StepAccounts />);

    await waitFor(() => expect(getPortfolio).toHaveBeenCalled());
    expect(useWizardStore.getState().data.accounts[0].basis).toBe(0);
    expect(useWizardStore.getState().data.accounts[1].basis).toBe(0);
    expect(screen.queryByTestId("basis-autofilled-0")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (c2) Review step: spouse birth date displays raw ISO string
// ---------------------------------------------------------------------------

describe("StepReview — date display", () => {
  it("renders spouse birth date '1964-08-22' verbatim without month offset", () => {
    act(() => {
      useWizardStore.getState().setField("household.filing_status", "joint");
      useWizardStore.getState().setField(
        "household.spouse_birth_date",
        "1964-08-22"
      );
    });

    render(<StepReview />);

    expect(screen.getByTestId("review-summary")).toHaveTextContent(/and 1964-08-22/);
  });
});

describe("StepReview — a summary with edit links, and no new questions", () => {
  it("summarises each step with a way back to it, including claim ages and the end year", async () => {
    act(() => {
      useWizardStore.getState().setField("household.self_birth_date", "1966-06-15");
      useWizardStore.getState().setField("household.spouse_birth_date", "1967-03-20");
      useWizardStore.getState().setField("household.filing_status", "joint");
      useWizardStore.setState({ step: 5, visitedMax: 5 });
    });
    render(<StepReview />);
    const summary = screen.getByTestId("review-summary");
    // Through 95 each: the spouse, born a year later, reaches it in 2062.
    expect(screen.getByTestId("review-horizon")).toHaveTextContent(
      "Planned through age 95 (you) and 95 (spouse) · projection ends in 2062");
    // Review only summarises: spending is asked on its own step.
    expect(screen.queryByLabelText(/How much would you like to spend/)).toBeNull();
    for (const part of ["household", "assumptions", "accounts", "income and social security",
                        "spending and goals"]) {
      expect(within(summary).getByRole("button", { name: `Edit ${part}` })).toBeInTheDocument();
    }
    expect((await within(summary).findAllByTestId("review-claim-line")).length).toBeGreaterThan(0);
    fireEvent.click(within(summary).getByRole("button", { name: "Edit accounts" }));
    expect(useWizardStore.getState().step).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// (d) Submit flow
// ---------------------------------------------------------------------------

/** The Review action waits for the claim-age preview; click once it can run. */
async function clickOptimize() {
  const btn = screen.getByTestId("review-submit");
  await waitFor(() => expect(btn).not.toBeDisabled(), { timeout: 3000 });
  fireEvent.click(btn);
}

describe("Submit flow (StepReview / step 5)", () => {
  // The Review step is reached with birth dates (step 1 requires them); the
  // claim-age preview needs them before the action can run.
  beforeEach(() => {
    act(() => {
      useWizardStore.getState().setField("household.self_birth_date", "1966-06-15");
      useWizardStore.getState().setField("household.spouse_birth_date", "1967-03-20");
    });
  });

  it("with an age searched, one action saves the plan and starts the background search", async () => {
    act(() => useWizardStore.getState().setClaimModes({ self: "search", spouse: "fixed" }));
    render(<StepReview />);
    expect(await screen.findByText("Compare 9 claim-age combinations")).toBeInTheDocument();
    expect(screen.getByTestId("review-submit")).toHaveTextContent(
      "Optimize conversions and claim ages"
    );
    await clickOptimize();
    await waitFor(() =>
      expect(submitOptimizeJob).toHaveBeenCalledWith(
        "hh-1", { self: { mode: "search" }, spouse: { mode: "fixed" } }, undefined
      )
    );
    expect(optimize).not.toHaveBeenCalled();
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/jobs/job-1"));
  });

  it("a running search is reported before the plan is saved", async () => {
    act(() => useWizardStore.getState().setClaimModes({ self: "search", spouse: "search" }));
    (getActiveOptimizeJob as jest.Mock).mockResolvedValue({ id: "other-job" });
    render(<StepReview />);
    await clickOptimize();
    expect(await screen.findByTestId("review-busy")).toHaveTextContent(/already running/);
    expect(createHousehold).not.toHaveBeenCalled();
  });

  it("both ages fixed: labelled as conversion optimization", async () => {
    render(<StepReview />);
    expect(await screen.findByText("Social Security ages held fixed")).toBeInTheDocument();
    expect(screen.getByTestId("review-submit")).toHaveTextContent(/^Optimize conversions$/);
  });

  it("a searched age with no comparison age is saved as none -- no age is invented", async () => {
    act(() => {
      useWizardStore.getState().setClaimModes({ self: "search", spouse: "search" });
      useWizardStore.getState().setField("settings.ss_claim_age_self", null);
      useWizardStore.getState().setField("settings.ss_claim_age_spouse", null);
    });
    render(<StepReview />);
    await clickOptimize();

    await waitFor(() => {
      expect(createHousehold).toHaveBeenCalledWith(
        expect.objectContaining({
          household: expect.objectContaining({ self_death_age: 95, spouse_death_age: 95 }),
          settings: expect.objectContaining({
            ss_claim_age_self: null,
            ss_claim_age_spouse: null,
            // displayed defaults must BE the stored values
            heir_tax_rate: 0.25,
          }),
        })
      );
    });
  });

  it("a single filer's plan is saved without leftover spouse fields", async () => {
    act(() => {
      useWizardStore.getState().setField("household.filing_status", "single");
      useWizardStore.getState().setField("settings.ss_pia_spouse", 1500);
    });
    render(<StepReview />);
    await clickOptimize();
    await waitFor(() => expect(createHousehold).toHaveBeenCalled());
    const saved = (createHousehold as jest.Mock).mock.calls[0][0];
    expect(saved.household).not.toHaveProperty("spouse_birth_date");
    expect(saved.household).not.toHaveProperty("spouse_death_age");
    expect(saved.settings).not.toHaveProperty("ss_pia_spouse");
    expect(saved.settings).not.toHaveProperty("ss_claim_age_spouse");
  });

  it("gains already realized are saved for this year, a loss as a negative amount", async () => {
    const { container, unmount } = render(<StepIncomeAndSS />);
    const field = (id: string) => container.querySelector(`#${id}`) as HTMLInputElement;
    fireEvent.change(field("gain-st"), { target: { value: "4000" } });
    fireEvent.click(screen.getByTestId("gain-st-loss"));
    fireEvent.change(field("gain-lt"), { target: { value: "25000" } });
    fireEvent.change(field("carry-lt"), { target: { value: "1500" } });
    unmount();

    render(<StepReview />);
    const year = new Date().getFullYear();
    expect(screen.getAllByTestId("review-gains-line")[0]).toHaveTextContent(
      `Gains realized in ${year} (− = loss): short-term −$4,000 · long-term $25,000`);
    await clickOptimize();
    await waitFor(() => expect(createHousehold).toHaveBeenCalled());
    expect((createHousehold as jest.Mock).mock.calls[0][0].capital_gains).toEqual({
      tax_year: year, short_term: -4000, long_term: 25000,
      carryover_short_term: 0, carryover_long_term: 1500,
    });
  });

  describe("a loss stays a loss however the amount is typed", () => {
    const enter = (container: HTMLElement, text: string) => {
      const input = container.querySelector("#gain-st") as HTMLInputElement;
      fireEvent.focus(input);
      fireEvent.change(input, { target: { value: text } });
      return input;
    };
    it.each(["-10,000", "$10,000", "10000", "-$10,000.00"])("%s, before and after leaving the field", (text) => {
      const { container } = render(<StepIncomeAndSS />);
      fireEvent.click(screen.getByTestId("gain-st-loss"));
      const input = enter(container, text);
      expect(useWizardStore.getState().data.capital_gains?.short_term).toBe(-10000);
      fireEvent.blur(input);
      expect(useWizardStore.getState().data.capital_gains?.short_term).toBe(-10000);
      // Switching back to Gain flips the sign, nothing else.
      fireEvent.click(screen.getByTestId("gain-st-gain"));
      expect(useWizardStore.getState().data.capital_gains?.short_term).toBe(10000);
    });
  });

  describe("a draft saved on December 31 and reopened on January 1", () => {
    // Only Date is faked: the claim preview and waitFor still need real timers.
    const onlyDate: { doNotFake: Config.FakeableAPI[] } = { doNotFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval",
      "setImmediate", "clearImmediate", "queueMicrotask", "nextTick", "hrtime", "performance",
      "requestAnimationFrame", "cancelAnimationFrame", "requestIdleCallback",
      "cancelIdleCallback"] };
    beforeEach(() => {
      jest.useFakeTimers({ ...onlyDate, now: new Date("2026-12-31T22:00:00") });
      act(() => useWizardStore.getState().setField("capital_gains", {
        tax_year: 2026, short_term: 0, long_term: 25000,
        carryover_short_term: 0, carryover_long_term: 0,
      }));
      jest.setSystemTime(new Date("2027-01-01T09:00:00"));
    });
    afterEach(() => jest.useRealTimers());

    it("keeps last year's figures under last year, says they do not apply, and edits stay 2026", async () => {
      const { container } = render(<StepIncomeAndSS />);
      expect(screen.getByTestId("realized-gains-title")).toHaveTextContent("realized in 2026");
      expect(screen.getByTestId("realized-gains-stale")).toHaveTextContent(
        "These figures are for 2026, which is over; a plan starting in 2027 does not apply them.");
      fireEvent.change(container.querySelector("#gain-lt") as HTMLInputElement,
        { target: { value: "40000" } });
      expect(useWizardStore.getState().data.capital_gains).toMatchObject(
        { tax_year: 2026, long_term: 40000 });
    });

    it("starting this year's entries is explicit, and clears last year's", () => {
      render(<StepIncomeAndSS />);
      fireEvent.click(screen.getByRole("button", { name: "Start 2027 entries" }));
      expect(useWizardStore.getState().data.capital_gains).toEqual({
        tax_year: 2027, short_term: 0, long_term: 0,
        carryover_short_term: 0, carryover_long_term: 0,
      });
      expect(screen.getByTestId("realized-gains-title")).toHaveTextContent("realized in 2027");
      expect(screen.queryByTestId("realized-gains-stale")).toBeNull();
    });

    it("a blank entry from last year is simply this year's", () => {
      act(() => useWizardStore.getState().setField("capital_gains.long_term", 0));
      const { container } = render(<StepIncomeAndSS />);
      expect(screen.getByTestId("realized-gains-title")).toHaveTextContent("realized in 2027");
      expect(screen.queryByTestId("realized-gains-stale")).toBeNull();
      fireEvent.change(container.querySelector("#gain-lt") as HTMLInputElement,
        { target: { value: "5000" } });
      expect(useWizardStore.getState().data.capital_gains).toMatchObject(
        { tax_year: 2027, long_term: 5000 });
    });
  });

  it("a plan with no gains entered saves none", async () => {
    render(<StepReview />);
    expect(screen.queryByTestId("review-gains-line")).toBeNull();
    await clickOptimize();
    await waitFor(() => expect(createHousehold).toHaveBeenCalled());
    expect((createHousehold as jest.Mock).mock.calls[0][0].capital_gains).toBeNull();
  });

  it("states which strategies are compared, with the fixed amounts in dollars", async () => {
    act(() => {
      useWizardStore.getState().setField("accounts.0.account_type", "traditional");
      useWizardStore.getState().setField("accounts.0.balance", 1_000_000);
    });
    render(<StepReview />);
    expect(screen.getByTestId("review-strategies")).toHaveTextContent(
      "We'll compare no conversions, tax-bracket strategies, and fixed annual conversion amounts " +
        "with different stopping years (up to $50,000, $100,000 or $200,000 a year: 5%, 10% or " +
        "20% of your starting traditional balance).");
    await screen.findByTestId("claim-setup");
  });

  it("Optimize button calls createHousehold, then optimize, then navigates to /results/<run_id>", async () => {
    render(<StepReview />);

    await clickOptimize();

    await waitFor(() => {
      expect(createHousehold as jest.Mock).toHaveBeenCalledTimes(1);
      expect(createHousehold).toHaveBeenCalledWith(
        expect.objectContaining({
          household: expect.objectContaining({
            filing_status: expect.any(String),
          }),
          accounts: expect.any(Array),
          settings: expect.any(Object),
          constraints: expect.any(Object),
        })
      );
    });

    await waitFor(() => {
      expect(optimize as jest.Mock).toHaveBeenCalledWith("hh-1", 300);
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/results/run-1");
    });
  });

  it("does NOT navigate if createHousehold throws", async () => {
    (createHousehold as jest.Mock).mockRejectedValue(
      new Error("Network error")
    );

    render(<StepReview />);
    await clickOptimize();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows inline error alert when optimize fails", async () => {
    (createHousehold as jest.Mock).mockResolvedValue({
      household_id: "hh-err",
    });
    (optimize as jest.Mock).mockRejectedValue(new Error("Optimizer error"));

    render(<StepReview />);
    await clickOptimize();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByText(/Optimizer error/i)).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// (e) NEW: Rail click navigates back to a previously-visited step
// ---------------------------------------------------------------------------

describe("ProgressRail navigation", () => {
  it("clicking a completed rail step navigates back to it", async () => {
    await renderWizard();

    // Manually advance store to step 1 with valid data
    act(() => {
      useWizardStore.getState().setField("household.self_birth_date", "1965-06-15");
      useWizardStore.getState().setField("household.spouse_birth_date", "1967-03-20");
      useWizardStore.getState().next(); // step=1, visitedMax=1
    });

    // We're on Planning Assumptions
    expect(screen.getByText("Planning Assumptions")).toBeInTheDocument();

    // The "Step 1: Household" rail node is now completed and clickable (desktop rail)
    const householdRailBtn = screen.getByRole("button", {
      name: /Step 1: Household \(completed\)/i,
    });
    fireEvent.click(householdRailBtn);

    // Back on Household Profile
    expect(screen.getByText("Household Profile")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (f) NEW: Invalid step blocks Next and shows inline error
// ---------------------------------------------------------------------------

describe("Zod validation — inline errors", () => {
  it("clicking Next without filling required fields shows an error and stays on step 0", async () => {
    await renderWizard();

    // Default state has empty self_birth_date → will fail step1Schema
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    // Error text appears under the self-birth-date field (exact match avoids collision with spouse error)
    expect(screen.getByText("Birth date is required")).toBeInTheDocument();

    // Still on step 0 — Household Profile visible
    expect(screen.getByText("Household Profile")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (g) NEW: Summary aside reflects a typed value
// ---------------------------------------------------------------------------

describe("SummaryAside live update", () => {
  it("reflects the store nickname in the summary aside", async () => {
    await renderWizard();

    act(() => {
      useWizardStore.getState().setField("household.nickname", "My Dream Plan");
    });

    // The aside should show the nickname
    const asideNickname = screen.getByTestId("aside-nickname");
    expect(asideNickname).toHaveTextContent("My Dream Plan");
  });
});

// ---------------------------------------------------------------------------
// (h) NEW: Draft banner appears when visitedMax > 0
// ---------------------------------------------------------------------------

const priorPlan = {
  household_id: "hh-prev",
  filing_status: "joint",
  state: "CA",
  created_at: "2026-06-01 00:00:00",
  nickname: "Old Plan",
};

describe("Wizard entry choice — no flash of the form", () => {
  // REGRESSION: clicking New Plan with saved plans briefly showed step 1
  // (Household Profile) before landing on the entry choice. The page rendered
  // the form immediately and only swapped it out when listHouseholds()
  // resolved, so the flash lasted exactly one network round-trip.
  it("never shows the form while deciding which screen to render", async () => {
    let release: (v: unknown[]) => void = () => {};
    (listHouseholds as jest.Mock).mockReturnValue(
      new Promise<unknown[]>((resolve) => {
        release = resolve;
      }),
    );

    render(<WizardPage />);

    // While the fetch is in flight: a placeholder, and NOT the wizard form.
    expect(screen.getByTestId("wizard-entry-loading")).toBeInTheDocument();
    expect(screen.queryByText("Household Profile")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Next/i })).toBeNull();

    await act(async () => {
      release([priorPlan]);
    });

    expect(screen.queryByTestId("wizard-entry-loading")).not.toBeInTheDocument();
    expect(screen.getByText(/start your new plan/i)).toBeInTheDocument();
  });

  it("falls through to the form when there are no saved plans", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([]);
    render(<WizardPage />);
    expect(await screen.findByText("Household Profile")).toBeInTheDocument();
  });

  it("falls through to the form when the plan list cannot be loaded", async () => {
    // A backend that cannot list plans must not block starting one.
    (listHouseholds as jest.Mock).mockRejectedValue(new Error("offline"));
    render(<WizardPage />);
    expect(await screen.findByText("Household Profile")).toBeInTheDocument();
  });
});

describe("Wizard entry choice (start fresh vs copy from plan)", () => {

  it("replaces the form with the choice when prior plans exist", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([priorPlan]);

    await act(async () => {
      render(<WizardPage />);
    });

    await waitFor(() => {
      expect(screen.getByTestId("wizard-entry-choice")).toBeInTheDocument();
    });
    // The form is NOT shown until a choice is made
    expect(screen.queryByText("Household Profile")).not.toBeInTheDocument();
  });

  it("caps the copy-from dropdown at the 10 newest plans", async () => {
    // Radix Select needs pointer-capture APIs jsdom lacks
    if (!Element.prototype.hasPointerCapture) {
      Element.prototype.hasPointerCapture = () => false;
      Element.prototype.releasePointerCapture = () => {};
    }
    if (!Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = () => {};
    }
    const many = Array.from({ length: 12 }, (_, i) => ({
      household_id: `hh-${i}`,
      filing_status: "joint",
      state: "CA",
      created_at: `2026-06-${String(28 - i).padStart(2, "0")} 00:00:00`,
      nickname: `Plan ${i}`,
    }));
    (listHouseholds as jest.Mock).mockResolvedValue(many);

    await act(async () => {
      render(<WizardPage />);
    });
    await waitFor(() => screen.getByTestId("wizard-entry-choice"));

    const trigger = screen.getByLabelText(/copy from/i);
    await act(async () => {
      trigger.focus();
      fireEvent.keyDown(trigger, { key: "Enter" });
    });

    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(10);
    expect(screen.queryByText(/Plan 10 /)).not.toBeInTheDocument();
    expect(screen.queryByText(/Plan 11/)).not.toBeInTheDocument();
  });

  it("'Copy this plan's inputs' loads the chosen plan and opens the form", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([priorPlan]);
    (getHousehold as jest.Mock).mockResolvedValue({
      household: {
        filing_status: "joint",
        self_birth_date: "1960-01-01",
        spouse_birth_date: "1962-01-01",
        state: "CA",
        nickname: "Prefilled Plan",
      },
      accounts: [],
      income: [],
      settings: {},
      constraints: {},
    });

    await act(async () => {
      render(<WizardPage />);
    });
    await waitFor(() => screen.getByTestId("wizard-entry-choice"));

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /copy this plan's inputs/i })
      );
    });

    await waitFor(() => {
      expect(getHousehold).toHaveBeenCalledWith("hh-prev");
      // Copied plans get a self-describing name so a forgotten rename
      // doesn't create a second plan with an identical nickname
      expect(useWizardStore.getState().data.household.nickname).toBe(
        "Copy of Prefilled Plan"
      );
      // Form is now visible
      expect(screen.getByText("Household Profile")).toBeInTheDocument();
    });
  });

  it("'Start fresh' opens a blank form without loading anything", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([priorPlan]);
    (getHousehold as jest.Mock).mockClear(); // this suite has no clearAllMocks

    await act(async () => {
      render(<WizardPage />);
    });
    await waitFor(() => screen.getByTestId("wizard-entry-choice"));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /start fresh/i }));
    });

    expect(getHousehold).not.toHaveBeenCalled();
    expect(screen.getByText("Household Profile")).toBeInTheDocument();
  });

  it("'Start fresh' discards a stale draft (regression)", async () => {
    // User-reported: a $400,000 cost basis kept reappearing in the wizard with
    // no portfolio uploaded.  loadFrom() sets visitedMax to 0, so a copied
    // plan's figures sat in the persisted draft while the draft banner — and
    // its "Start over" button — stayed hidden.  EntryChoice was the only exit,
    // and "Start fresh" merely dismissed the chooser without clearing data.
    (listHouseholds as jest.Mock).mockResolvedValue([priorPlan]);

    // Stale draft: populated figures, but visitedMax still 0 (as loadFrom leaves it).
    act(() => {
      useWizardStore.getState().setField("accounts.0.basis", 400000);
      useWizardStore.getState().setField("accounts.0.balance", 1000000);
    });
    expect(useWizardStore.getState().visitedMax).toBe(0);

    await act(async () => {
      render(<WizardPage />);
    });
    await waitFor(() => screen.getByTestId("wizard-entry-choice"));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /start fresh/i }));
    });

    expect(useWizardStore.getState().data.accounts[0].basis).toBe(0);
    expect(useWizardStore.getState().data.accounts[0].balance).toBe(0);
  });

  it("copied plan with DB-null claim age can pass Review (regression)", async () => {
    // User-reported bug: copying a plan whose ss_claim_age_spouse was NULL in
    // the DB silently blocked the Review button on the Income step — zod
    // rejected the null and the failing field had no visible error slot.
    (listHouseholds as jest.Mock).mockResolvedValue([priorPlan]);
    (getHousehold as jest.Mock).mockResolvedValue({
      household_id: "hh-prev",
      household: {
        filing_status: "joint",
        self_birth_date: "1962-12-19",
        spouse_birth_date: "1966-12-24",
        state: "CA",
        nickname: "First",
      },
      accounts: [
        { account_type: "taxable", owner: "joint", balance: 1000000, basis: 800000 },
        { account_type: "traditional", owner: "self", balance: 500000, basis: null },
      ],
      income: [
        { category: "qualified_dividend", owner: "spouse", amount: 45000,
          start_year: null, end_year: null },
      ],
      settings: {
        required_spending: 120000,
        inflation: 0.03,
        nominal_return: 0.06,
        ss_pia_self: 3500,
        ss_claim_age_self: 67,
        ss_pia_spouse: 2000,
        ss_claim_age_spouse: null, // ← the poison value
        // Self is past 62: whether benefits started must be answered.
        ss_receiving_self: false,
      },
      constraints: {},
    });

    await act(async () => {
      render(<WizardPage />);
    });
    await waitFor(() => screen.getByTestId("wizard-entry-choice"));
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /copy this plan's inputs/i })
      );
    });
    await waitFor(() => screen.getByText("Household Profile"));

    // Jump to the Income step (index 3) as the user did via Next clicks. The
    // null spouse age is a searched age with no comparison age.
    act(() => {
      useWizardStore.getState().setClaimModes({ self: "search", spouse: "search" });
      useWizardStore.setState({ step: 3, visitedMax: 3 });
    });
    expect(screen.getByText(/Income & Social Security/i)).toBeInTheDocument();
    expect(useWizardStore.getState().data.settings.ss_claim_age_spouse).toBeNull();

    // Next must ADVANCE to Spending and goals, not stall
    fireEvent.click(screen.getByRole("button", { name: /^Next$/ }));
    expect(screen.getByText("Spending and goals")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Review$/ }));
    expect(screen.getByText("Review and run")).toBeInTheDocument();
  });

  it("blocked Next shows a step-level error summary (never silent)", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([]);

    await act(async () => {
      render(<WizardPage />);
    });
    await waitFor(() => screen.getByText("Household Profile"));

    // Force an invalid value for the CURRENT step and click Next
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    // The summary lists what's wrong near the footer
    const summary = screen.getByTestId("step-error-summary");
    expect(summary).toBeInTheDocument();
    expect(summary).toHaveTextContent(/fix before continuing/i);
  });

  it("a Roth with a balance needs its year opened, named plainly in the summary", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([]);
    await act(async () => {
      render(<WizardPage />);
    });
    await waitFor(() => screen.getByText("Household Profile"));
    act(() => {
      useWizardStore.getState().setField("accounts", [
        { account_type: "roth", owner: "self", balance: 50000, roth_opened_year: null },
      ]);
      useWizardStore.setState({ step: 2, visitedMax: 2 });
    });
    fireEvent.click(screen.getByRole("button", { name: /^Next$/ }));
    expect(screen.getByTestId("step-error-summary")).toHaveTextContent(
      "Account 1 · year Roth opened: Enter the year this Roth was first opened"
    );
  });

  it("goes straight to the form when there are no prior plans", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([]);

    await act(async () => {
      render(<WizardPage />);
    });

    await waitFor(() => {
      expect(listHouseholds).toHaveBeenCalled();
    });

    expect(screen.queryByTestId("wizard-entry-choice")).not.toBeInTheDocument();
    expect(screen.getByText("Household Profile")).toBeInTheDocument();
  });
});

describe("Draft resume banner", () => {
  it("shows the draft banner when the store has a non-zero visitedMax", () => {
    // Set visitedMax > 0 before rendering (simulates a resumed draft)
    act(() => {
      useWizardStore.setState({ visitedMax: 2, step: 0 });
    });

    render(<WizardPage />);

    expect(screen.getByText(/Resuming your saved draft/i)).toBeInTheDocument();
  });

  it("clicking 'Start over' on the banner resets the store and hides the banner", () => {
    act(() => {
      useWizardStore.setState({ visitedMax: 1, step: 0 });
    });

    render(<WizardPage />);

    expect(screen.getByText(/Resuming your saved draft/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Start over/i }));

    expect(
      screen.queryByText(/Resuming your saved draft/i)
    ).not.toBeInTheDocument();
    expect(useWizardStore.getState().visitedMax).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Objective knobs on the Assumptions step
// ---------------------------------------------------------------------------

describe("Collapsed list entries", () => {
  it("a complete account collapses to an editable summary; the one being typed into stays open", () => {
    act(() => {
      useWizardStore.getState().setField("accounts.0.account_type", "traditional");
      useWizardStore.getState().setField("accounts.0.balance", 500000);
    });
    render(<StepAccounts />);
    expect(screen.getByTestId("account-summary-0")).toHaveTextContent(
      "Traditional IRA / 401(k) · you · $500,000");

    // A new account opens, and stays open while its balance is typed.
    fireEvent.click(screen.getByRole("button", { name: /Add Account/i }));
    act(() => {
      useWizardStore.getState().setField("accounts.1.balance", 1000);
    });
    expect(screen.queryByTestId("account-summary-1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.getByTestId("account-summary-1")).toBeInTheDocument();

    // Edit reopens the first.
    fireEvent.click(screen.getByRole("button", { name: "Edit account 1" }));
    expect(screen.queryByTestId("account-summary-0")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Balance/)).toBeInTheDocument();
  });

  it("income reads as one line: whose, what, how much, which years", () => {
    act(() => {
      useWizardStore.getState().addIncome();
      useWizardStore.getState().setField("income.0.category", "salary");
      useWizardStore.getState().setField("income.0.owner", "self");
      useWizardStore.getState().setField("income.0.amount", 100000);
      useWizardStore.getState().setField("income.0.start_year", 2026);
      useWizardStore.getState().setField("income.0.end_year", 2028);
    });
    render(<StepIncomeAndSS />);
    expect(screen.getByTestId("income-summary-0")).toHaveTextContent(
      "Your salary · $100,000/year · 2026–2028");
  });
});

describe("StepAssumptions advanced settings", () => {
  it("shows advanced settings without a disclosure, and explains IRMAA as a cliff", async () => {
    const { StepAssumptions } = require("@/components/wizard/steps");
    render(<StepAssumptions />);
    const adv = screen.getByTestId("advanced-assumptions");
    expect(adv.tagName).toBe("SECTION");
    expect(adv.querySelector("summary")).toBeNull();
    expect(adv).toHaveTextContent("Advanced settings");
    expect(screen.getByLabelText("Heir Tax Rate")).toBeVisible();
    const group = screen.getByTestId("irmaa-policy");
    act(() => within(group).getByRole("button", { name: "More info" }).focus());
    expect((await screen.findAllByText(/works as a cliff/)).length).toBeGreaterThan(0);
  });

  it("shows optional goals and limits without a disclosure", () => {
    const { StepSpendingGoals } = require("@/components/wizard/steps");
    render(<StepSpendingGoals />);
    const limits = screen.getByTestId("advanced-limits");
    expect(limits.tagName).toBe("SECTION");
    expect(limits.querySelector("summary")).toBeNull();
    expect(limits).toHaveTextContent("Optional goals and limits");
  });

  it("offers the two Medicare surcharge behaviours, and an older value keeps its own", () => {
    const { StepAssumptions } = require("@/components/wizard/steps");
    act(() => useWizardStore.getState().setField("constraints.irmaa_policy", "avoid"));
    render(<StepAssumptions />);
    const group = screen.getByTestId("irmaa-policy");
    expect(within(group).getAllByRole("radio")).toHaveLength(2);
    expect(group).toHaveTextContent("Allow conversions to cross Medicare surcharge thresholds");
    expect(group).toHaveTextContent("The model includes the surcharge cost.");
    // "avoid" behaves as "strict": shown as Restrict, saved unchanged.
    expect(screen.getByTestId("irmaa-strict")).toBeChecked();
    expect(useWizardStore.getState().data.constraints.irmaa_policy).toBe("avoid");
    fireEvent.click(screen.getByTestId("irmaa-soft"));
    expect(useWizardStore.getState().data.constraints.irmaa_policy).toBe("soft");
  });
});

describe("StepAssumptions objective knobs", () => {
  it("renders Heir Tax Rate and no longer offers an optimization priority", () => {
    // The Estate / Balanced / Lifetime-taxes priority was retired: taxes are
    // already out of the after-tax estate the optimizer maximizes.
    const { StepAssumptions } = require("@/components/wizard/steps");
    render(<StepAssumptions />);

    expect(screen.getByLabelText(/Heir Tax Rate/i)).toBeInTheDocument();
    expect(screen.queryByText("Optimization Priority")).toBeNull();
    expect(screen.queryByRole("radio", { name: /Lifetime taxes/i })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Dynamic spending controls
// ---------------------------------------------------------------------------

describe("StepSpendingGoals", () => {
  it("asks what to spend, says what the amount includes, and promises no funding", () => {
    render(<StepSpendingGoals />);
    expect(screen.getByLabelText("How much would you like to spend each year?")).toBeInTheDocument();
    expect(screen.getByText(/before subtracting Social Security or other income/)).toBeInTheDocument();
    expect(screen.getByText(/excluding income taxes/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/ensures this is funded/);
  });

  it("defaults to fixed spending and hides the minimum", () => {
    render(<StepSpendingGoals />);

    expect(
      screen.getByRole("radio", { name: /Keep spending the same/i })
    ).toHaveAttribute("aria-checked", "true");
    // The minimum only means anything once spending can flex.
    expect(screen.queryByLabelText(/Minimum annual spending/i)).toBeNull();
  });

  it("choosing guardrails stores the rule and reveals the minimum, explaining a blank", () => {
    render(<StepSpendingGoals />);

    fireEvent.click(screen.getByRole("radio", { name: /Cut back, then recover/i }));

    expect(useWizardStore.getState().data.settings.spending_rule).toBe(
      "guardrails"
    );
    expect(screen.getByLabelText(/Minimum annual spending/i)).toBeInTheDocument();
    expect(screen.getByText(/Planned spending cuts will not go below this amount/)).toBeInTheDocument();
    expect(screen.getByText(/Leave it blank for no minimum/)).toBeInTheDocument();
  });

  it("rejects a minimum above annual spending, only when spending can be cut", () => {
    act(() => {
      useWizardStore.getState().setField("settings.required_spending", 100000);
      useWizardStore.getState().setField("settings.spending_floor", 150000);
    });
    const data = () => useWizardStore.getState().data;
    expect(validateStep(4, data()).success).toBe(true);
    act(() => useWizardStore.getState().setField("settings.spending_rule", "guardrails"));
    expect(validateStep(4, data()).errors).toEqual({
      spending_floor: "The minimum cannot be more than your annual spending",
    });
  });
});

describe("StepProfile — plan-through ages", () => {
  it("starts at a visible default of 95, says what it means, and requires it", () => {
    act(() => {
      useWizardStore.getState().setField("household.self_birth_date", "1966-06-15");
      useWizardStore.getState().setField("household.spouse_birth_date", "1967-03-20");
    });
    render(<StepProfile />);
    expect(screen.getByLabelText("Plan through age (you)")).toHaveValue(95);
    expect(screen.getByLabelText("Plan through age (spouse)")).toHaveValue(95);
    expect(screen.getByTestId("plan-through-help")).toHaveTextContent(
      "This is a planning assumption, not a prediction of lifespan.");
    expect(screen.getByTestId("plan-through-help")).toHaveTextContent("runs through 2062");
    expect(document.body).not.toHaveTextContent(/stays solvent/);

    act(() => useWizardStore.getState().setField("household.spouse_death_age", null));
    expect(validateStep(0, useWizardStore.getState().data).errors).toEqual({
      spouse_death_age: "Enter the age to plan through",
    });
  });
});

// ---------------------------------------------------------------------------
// Social Security step: explicit receiving answer and the claim-age choice
// ---------------------------------------------------------------------------

describe("StepIncomeAndSS — claim-age setup", () => {
  beforeEach(() => {
    act(() => {
      useWizardStore.getState().setField("household.filing_status", "joint");
      useWizardStore.getState().setField("household.self_birth_date", `${new Date().getFullYear() - 64}-01-01`);
      useWizardStore.getState().setField("household.spouse_birth_date", "1990-01-01");
      // The questions after the benefit appear once it is entered.
      useWizardStore.getState().setField("settings.ss_pia_spouse", 1500);
      useWizardStore.getState().setClaimModes({ self: "search", spouse: "search" });
    });
  });

  it("asks 'already receiving?' first; Yes asks when benefits started, and nothing else", async () => {
    render(<StepIncomeAndSS />);
    expect(screen.getByText("Already receiving Social Security?")).toBeInTheDocument();
    expect(screen.getByText("Not answered yet")).toBeInTheDocument();
    // Unanswered: how to choose the age is not asked yet.
    expect(screen.queryByTestId("claim-mode-self-search")).toBeNull();
    // The spouse is under 62: not asked, straight to how to choose.
    expect(screen.queryByText("Spouse already receiving Social Security?")).toBeNull();
    expect(screen.getByTestId("claim-mode-spouse-search")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("ss-receiving-self-yes"));
    expect(useWizardStore.getState().data.settings.ss_receiving_self).toBe(true);
    expect(screen.getByText("At what age did benefits start?")).toBeInTheDocument();
    expect(screen.queryByTestId("claim-mode-self-search")).toBeNull();
    await screen.findByTestId("claim-setup");
  });

  it("No: choose how, and the age selector appears only for 'Use an age I choose'", async () => {
    act(() => useWizardStore.getState().setField("settings.ss_claim_age_spouse", null));
    render(<StepIncomeAndSS />);
    const spouse = screen.getByTestId("ss-person-spouse");
    // Searched: an optional comparison age, "No comparison" when blank.
    expect(within(spouse).getByText(/Have a claim age in mind\?/)).toBeInTheDocument();
    expect(within(spouse).getByText("We'll compare the recommendation with your choice.")).toBeInTheDocument();
    expect(within(spouse).getByTestId("ss-compare-spouse")).toHaveTextContent("No comparison");
    expect(within(spouse).queryByLabelText("Claim age")).toBeNull();
    fireEvent.click(within(spouse).getByTestId("claim-mode-spouse-fixed"));
    expect(within(spouse).getByLabelText("Claim age")).toBeInTheDocument();
    expect(within(spouse).queryByText(/Have a claim age in mind\?/)).toBeNull();
    // Chosen but not given: required.
    expect(validateStep(3, useWizardStore.getState().data, useWizardStore.getState().claimModes)
      .errors.ss_claim_age_spouse).toBe("Choose a claim age, or let the optimizer find the best one");
    await screen.findByTestId("claim-setup");
  });

  it("labels the benefit as the full-retirement-age amount", async () => {
    render(<StepIncomeAndSS />);
    expect(screen.getByText("Your monthly benefit at full retirement age")).toBeInTheDocument();
    await screen.findByTestId("claim-setup");
  });

  it("switching to 'Use an age I choose' keeps the entered age", async () => {
    render(<StepIncomeAndSS />);
    fireEvent.click(screen.getByTestId("ss-receiving-self-no"));
    await screen.findByTestId("claim-mode-self-search");
    expect(await screen.findByTestId("claim-setup-summary")).toHaveTextContent("Compare 81 claim-age combinations");
    fireEvent.click(screen.getByTestId("claim-mode-self-fixed"));
    expect(useWizardStore.getState().claimModes.self).toBe("fixed");
    expect(useWizardStore.getState().data.settings.ss_claim_age_self).toBe(67);
    expect(screen.getByTestId("claim-setup-summary")).toHaveTextContent("You: 67 (your chosen age)");
  });
});

// ---------------------------------------------------------------------------
// Review reliability: stale previews, mixed setups, busy after saving
// ---------------------------------------------------------------------------

describe("Review — only a current, successful preview can start a run", () => {
  beforeEach(() => {
    act(() => {
      useWizardStore.getState().setField("household.self_birth_date", "1966-06-15");
      useWizardStore.getState().setField("household.spouse_birth_date", "1967-03-20");
    });
  });

  it("an edit disables the action until the new preview arrives", async () => {
    render(<StepReview />);
    const btn = screen.getByTestId("review-submit");
    await waitFor(() => expect(btn).not.toBeDisabled(), { timeout: 3000 });
    // The refresh for the edited inputs never answers: the old preview stays
    // on screen, but it describes other inputs.
    (previewClaimAges as jest.Mock).mockReturnValue(new Promise(() => {}));
    act(() => useWizardStore.getState().setField("settings.ss_claim_age_self", 70));
    expect(btn).toBeDisabled();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 600));
    });
    expect(btn).toBeDisabled();
  });

  it("a failed refresh keeps the action disabled and says why", async () => {
    render(<StepReview />);
    const btn = screen.getByTestId("review-submit");
    await waitFor(() => expect(btn).not.toBeDisabled(), { timeout: 3000 });
    (previewClaimAges as jest.Mock).mockRejectedValue(new Error("HTTP 500: boom"));
    act(() => useWizardStore.getState().setField("settings.ss_claim_age_self", 70));
    expect(await screen.findByTestId("claim-setup-error", {}, { timeout: 3000 })).toHaveTextContent("boom");
    expect(btn).toBeDisabled();
  });

  it("a fixed age the search would skip, beside a searched one, is blocked before saving", async () => {
    (previewClaimAges as jest.Mock).mockResolvedValue({
      self: {
        status: "searchable", age: 62, entered_age: 64, receiving: false, pia: 2000,
        ages: [65, 66, 67, 68, 69, 70],
        exclusions: [{ age: 64, reason: "salary paid 2028, before full retirement age" }],
        message: null,
      },
      spouse: {
        status: "searchable", age: 61, entered_age: 67, receiving: false, pia: 1000,
        ages: [62, 63, 64, 65, 66, 67, 68, 69, 70], exclusions: [], message: null,
      },
    });
    act(() => useWizardStore.getState().setClaimModes({ self: "fixed", spouse: "search" }));
    render(<StepReview />);
    expect(await screen.findByText(/the chosen age 64 is skipped by the search/)).toBeInTheDocument();
    expect(screen.getByTestId("review-submit")).toBeDisabled();
    expect(createHousehold).not.toHaveBeenCalled();
  });

  it("busy after saving keeps the draft, explains, and retries without a second copy", async () => {
    act(() => useWizardStore.getState().setClaimModes({ self: "search", spouse: "fixed" }));
    (submitOptimizeJob as jest.Mock).mockClear();
    (submitOptimizeJob as jest.Mock).mockRejectedValueOnce(
      new ApiError(409, '{"detail":{"message":"busy","job_id":"other-job"}}')
    );
    render(<StepReview />);
    await clickOptimize();

    expect(await screen.findByTestId("review-saved-busy")).toHaveTextContent(
      /saved, but its search has not started/
    );
    expect(mockPush).not.toHaveBeenCalled();
    // The draft is still there to retry from.
    expect(useWizardStore.getState().data.household.self_birth_date).toBe("1966-06-15");

    await clickOptimize();
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/jobs/job-1"));
    expect(createHousehold).toHaveBeenCalledTimes(1);
    expect(submitOptimizeJob).toHaveBeenCalledTimes(2);
    expect((submitOptimizeJob as jest.Mock).mock.calls[1][0]).toBe("hh-1");
  });
});


// ---------------------------------------------------------------------------
// Finishing a plan that was saved but never run (dashboard → Review)
// ---------------------------------------------------------------------------

describe("Finish setup and run — a saved plan with no completed run", () => {
  const year = new Date().getFullYear();
  const saved = () => ({
    household_id: "hh-saved",
    household: {
      filing_status: "joint", self_birth_date: `${year - 60}-01-01`, spouse_birth_date: `${year - 58}-01-01`,
      state: "CA", nickname: "Unfinished", self_death_age: 95, spouse_death_age: 95,
    },
    accounts: [{ account_type: "traditional", owner: "self", balance: 1000000, basis: null }],
    income: [],
    settings: {
      required_spending: 90000, inflation: 0.03, nominal_return: 0.06,
      ss_pia_self: 3000, ss_claim_age_self: 67, ss_pia_spouse: 1500, ss_claim_age_spouse: null,
      ss_receiving_self: null, ss_receiving_spouse: null, heir_tax_rate: 0.25, spending_rule: "fixed",
    },
    constraints: { irmaa_policy: "soft", conversion_window: "anytime", preserve_taxable: false },
  });

  beforeEach(() => {
    localStorage.clear();
    useWizardStore.getState().reset();
    window.history.pushState({}, "", "/wizard?resume=hh-saved");
    (getHousehold as jest.Mock).mockReset().mockResolvedValue(saved());
    (updateHousehold as jest.Mock).mockReset().mockResolvedValue({});
    (submitOptimizeJob as jest.Mock).mockClear();
  });
  afterEach(() => window.history.pushState({}, "", "/"));

  async function openResumed() {
    const utils = render(<WizardPage />);
    await screen.findByText("Review and run");
    return utils;
  }

  it("opens Review for that plan with its recorded choices, and runs it without saving a copy", async () => {
    savePlanModes("hh-saved", { self: "fixed", spouse: "search" });
    await openResumed();
    expect(screen.getByTestId("resume-banner")).toHaveTextContent("Finishing setup for Unfinished");
    // The plan itself, not a "Copy of".
    expect(useWizardStore.getState().data.household.nickname).toBe("Unfinished");
    expect(useWizardStore.getState().claimModes).toEqual({ self: "fixed", spouse: "search" });
    expect(screen.queryByTestId("review-confirm-modes")).toBeNull();

    await clickOptimize();
    await waitFor(() => expect(submitOptimizeJob).toHaveBeenCalledWith(
      "hh-saved", { self: { mode: "fixed" }, spouse: { mode: "search" } }, undefined));
    expect(createHousehold).not.toHaveBeenCalled();
    expect(updateHousehold).not.toHaveBeenCalled();
  });

  it("without recorded choices, asks for those it cannot deduce before running", async () => {
    await openResumed();
    // Spouse: no age stored, so it was "find the best age". You: 67 stored --
    // a choice or a comparison? Asked, not assumed.
    expect(useWizardStore.getState().unconfirmedModes).toEqual(["self"]);
    expect(useWizardStore.getState().claimModes.spouse).toBe("search");
    const confirm = screen.getByTestId("review-confirm-modes");
    expect(confirm).toHaveTextContent("Confirm how each claim age is chosen");
    const btn = screen.getByTestId("review-submit");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 600));
    });
    expect(btn).toBeDisabled();
    fireEvent.click(screen.getByTestId("confirm-self-fixed"));
    expect(screen.queryByTestId("review-confirm-modes")).toBeNull();
    await clickOptimize();
    await waitFor(() => expect(submitOptimizeJob).toHaveBeenCalledWith(
      "hh-saved", { self: { mode: "fixed" }, spouse: { mode: "search" } }, undefined));
    expect(createHousehold).not.toHaveBeenCalled();
  });

  it("survives leaving and reloading: the draft still belongs to the plan, and an edit updates it in place", async () => {
    savePlanModes("hh-saved", { self: "search", spouse: "search" });
    const first = await openResumed();
    first.unmount();                       // left the wizard
    (getHousehold as jest.Mock).mockClear();
    await openResumed();                   // came back to the same link
    expect(getHousehold).not.toHaveBeenCalled();
    expect(useWizardStore.getState().resume?.householdId).toBe("hh-saved");

    act(() => useWizardStore.getState().setField("settings.required_spending", 95000));
    await clickOptimize();
    await waitFor(() => expect(updateHousehold).toHaveBeenCalledWith(
      "hh-saved", expect.objectContaining({
        settings: expect.objectContaining({ required_spending: 95000 }) })));
    await waitFor(() => expect(submitOptimizeJob).toHaveBeenCalled());
    expect((submitOptimizeJob as jest.Mock).mock.calls[0][0]).toBe("hh-saved");
    expect(createHousehold).not.toHaveBeenCalled();
  });

  it("a plan saved by Review and refused as busy is reused after leaving the wizard", async () => {
    window.history.pushState({}, "", "/wizard");
    act(() => {
      useWizardStore.getState().setField("household.self_birth_date", "1966-06-15");
      useWizardStore.getState().setField("household.spouse_birth_date", "1967-03-20");
      useWizardStore.getState().setField("settings.ss_claim_age_self", 67);
      useWizardStore.getState().setField("settings.ss_claim_age_spouse", 67);
      useWizardStore.getState().setClaimModes({ self: "search", spouse: "fixed" });
    });
    (submitOptimizeJob as jest.Mock).mockRejectedValueOnce(
      new ApiError(409, '{"detail":{"message":"busy","job_id":"other-job"}}'));
    const first = render(<StepReview />);
    await clickOptimize();
    expect(await screen.findByTestId("review-saved-busy")).toHaveTextContent(/Finish setup and run/);
    first.unmount();
    // The dashboard's link back to it:
    window.history.pushState({}, "", "/wizard?resume=hh-1");
    await openResumed();
    await clickOptimize();
    await waitFor(() => expect(submitOptimizeJob).toHaveBeenCalledTimes(2));
    expect((submitOptimizeJob as jest.Mock).mock.calls[1][0]).toBe("hh-1");
    expect(createHousehold).toHaveBeenCalledTimes(1);
    expect(getHousehold).not.toHaveBeenCalled();
  });
});
