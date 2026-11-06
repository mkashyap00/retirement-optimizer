/**
 * @jest-environment jsdom
 *
 * RTL tests for the LLM narrative feature on the results page.
 *
 * Covers:
 *   - "Generate AI summary" button shown when health.llm === true
 *   - Button hidden when health.llm === false
 *   - Click → POST narrative → narrative card rendered
 */

// --- Module mocks (hoisted before imports) -----------------------------------

jest.mock("@/lib/api", () => ({
  getRun: jest.fn(),
  getHealth: jest.fn(),
  generateNarrative: jest.fn(),
  optimize: jest.fn(),
  listRuns: jest.fn().mockResolvedValue([]),
  BASE_URL: "http://localhost:8000",
}));

// The run id comes from the route via useParams: from Next 15 a page's
// `params` prop is a Promise, so a client page cannot read it synchronously.
jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
  useParams: () => ({ runId: "run-123" }),
}));

// Mock recharts to avoid canvas errors in jsdom
jest.mock("recharts", () => {
  const React = require("react");
  const FakeChart = ({ children }: { children?: React.ReactNode }) =>
    React.createElement("div", { "data-testid": "chart" }, children);
  FakeChart.displayName = "FakeChart";
  return {
    ResponsiveContainer: FakeChart,
    AreaChart: FakeChart,
    BarChart: FakeChart,
    LineChart: FakeChart,
    Area: () => null,
    Bar: () => null,
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
    ReferenceLine: () => null,
  };
});

// --- Imports -----------------------------------------------------------------

import React from "react";
import "@testing-library/jest-dom";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { useRouter } from "next/navigation";
import { getRun, getHealth, generateNarrative, optimize, listRuns } from "@/lib/api";
import ResultsPage from "@/app/results/[runId]/page";
import type { OptimizationResult } from "@/lib/types";

const mockPush = jest.fn();

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

// --- Fixture -----------------------------------------------------------------

const minimalResult: OptimizationResult = {
  status: "ok",
  computation_time_seconds: 0.5,
  paths_evaluated: 10,
  monte_carlo_runs: 1,
  winning_policy: {
    policy_id: "p1",
    lifetime_taxes_nominal: 100000,
    lifetime_taxes_pv: 80000,
    terminal_estate: 500000,
    success_probability: 0.9,
    score: 0.85,
    total_conversions: 20000,
    projected_future_marginal_rate: 0.22,
  },
  yearly_plan: [],
  alternative_policies: [],
  warnings: [],
};

// --- Tests -------------------------------------------------------------------

const mockGetRun = getRun as jest.MockedFunction<typeof getRun>;
const mockGetHealth = getHealth as jest.MockedFunction<typeof getHealth>;
const mockGenerateNarrative = generateNarrative as jest.MockedFunction<typeof generateNarrative>;

function renderPage() {
  return render(<ResultsPage />);
}

beforeEach(() => {
  jest.clearAllMocks();
  (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  // Default: run loads successfully — use backend-style timestamp (space separator, microseconds)
  mockGetRun.mockResolvedValue({
    run_id: "run-123",
    household_id: "hh-1",
    created_at: "2026-07-05 16:29:17.920023",
    result: minimalResult,
  });
});

describe("Results page header", () => {
  it("titles the page with the plan and keeps the IDs in Run details", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });

    await act(async () => {
      renderPage();
    });

    // Wait for the run to load
    await waitFor(() => screen.getByTestId("results-title"));

    // No nickname in this fixture: a plain title. The IDs sit in the
    // collapsed "Run details", not under the title.
    expect(screen.getByTestId("results-title")).toHaveTextContent("Optimization results");
    expect(screen.getByTestId("run-details")).not.toHaveAttribute("open");
    // created_at "2026-07-05 16:29:17.920023" → "Run created Jul 5, 2026"
    const runCreatedEl = screen.getByText(/Run created/i);
    expect(runCreatedEl).toBeInTheDocument();
    expect(runCreatedEl.textContent).toContain("Jul 5, 2026");
    expect(runCreatedEl.textContent).toContain("4:29");
  });
});

describe("Generate AI summary button — health.llm true", () => {
  it("shows the button when health.llm is true", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: true });

    await act(async () => {
      renderPage();
    });

    await waitFor(() =>
      expect(screen.getByTestId("generate-ai-summary")).toBeInTheDocument()
    );
  });

  it("clicking the button calls generateNarrative and renders the card", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: true });
    mockGenerateNarrative.mockResolvedValue({
      narrative: "Here is your AI summary.",
    });

    await act(async () => {
      renderPage();
    });

    await waitFor(() =>
      expect(screen.getByTestId("generate-ai-summary")).toBeInTheDocument()
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("generate-ai-summary"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("narrative-card")).toBeInTheDocument()
    );

    expect(screen.getByText("Here is your AI summary.")).toBeInTheDocument();
    expect(mockGenerateNarrative).toHaveBeenCalledWith("run-123");
  });
});

describe("Generate AI summary button — health.llm false", () => {
  it("hides the button when health.llm is false", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });

    await act(async () => {
      renderPage();
    });

    // Wait for the run to load so we know the page is fully rendered
    await waitFor(() => screen.getByTestId("results-title"));

    expect(screen.queryByTestId("generate-ai-summary")).not.toBeInTheDocument();
  });

  it("hides the button when getHealth rejects", async () => {
    mockGetHealth.mockRejectedValue(new Error("Network error"));

    await act(async () => {
      renderPage();
    });

    await waitFor(() => screen.getByTestId("results-title"));

    expect(screen.queryByTestId("generate-ai-summary")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Inputs snapshot panel
// ---------------------------------------------------------------------------

const snapshotInputs = {
  household_id: "hh-1",
  household: {
    filing_status: "joint" as const,
    self_birth_date: "1958-03-15",
    spouse_birth_date: "1960-03-15",
    state: "CA",
    nickname: "Demo",
  },
  accounts: [
    { account_type: "traditional" as const, owner: "joint" as const, balance: 800000 },
  ],
  income: [
    { category: "pension" as const, owner: "self" as const, amount: 20000 },
  ],
  settings: {
    required_spending: 90000,
    inflation: 0.025,
    nominal_return: 0.06,
    ss_pia_self: 2400,
    ss_claim_age_self: 67,
  },
  constraints: {
    irmaa_policy: "soft" as const,
    conversion_window: "anytime" as const,
    preserve_taxable: false,
  },
};

describe("Inputs snapshot panel", () => {
  it("renders collapsed when the run carries inputs; expands on click", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
    mockGetRun.mockResolvedValue({
      run_id: "run-123",
      household_id: "hh-1",
      created_at: "2026-07-05 16:29:17.920023",
      result: minimalResult,
      inputs: snapshotInputs,
    });

    await act(async () => {
      renderPage();
    });
    await waitFor(() => screen.getByTestId("results-title"));

    // Toggle present, body collapsed
    const toggle = screen.getByTestId("inputs-panel-toggle");
    expect(toggle).toBeInTheDocument();
    expect(screen.queryByTestId("inputs-panel-body")).not.toBeInTheDocument();

    // Expand → snapshot values visible (spending, account balance)
    fireEvent.click(toggle);
    expect(screen.getByTestId("inputs-panel-body")).toBeInTheDocument();
    expect(screen.getByText("$90,000")).toBeInTheDocument();
    expect(screen.getByText("$800,000")).toBeInTheDocument();
  });

  it("hides the panel for old runs without an inputs snapshot", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
    // default beforeEach mock has no `inputs` key

    await act(async () => {
      renderPage();
    });
    await waitFor(() => screen.getByTestId("results-title"));

    expect(screen.queryByTestId("inputs-panel-toggle")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Alternative Policies table + forced-policy runs
// ---------------------------------------------------------------------------

const resultWithAlternatives = {
  ...minimalResult,
  alternative_policies: [
    {
      policy_id: "fill_22",
      lifetime_taxes_delta: -246291,
      terminal_estate_delta: -262671,
      success_probability_delta: 0.02,
    },
  ],
};

describe("Alternative Policies table", () => {
  it("renders the runners-up with humanized names and deltas", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
    mockGetRun.mockResolvedValue({
      run_id: "run-123",
      household_id: "hh-1",
      created_at: "2026-07-05 16:29:17.920023",
      result: resultWithAlternatives,
    });

    await act(async () => {
      renderPage();
    });
    await waitFor(() => screen.getByTestId("results-title"));

    const table = screen.getByTestId("alternatives-table");
    expect(table).toHaveTextContent("Fill the 22% bracket");
    expect(table).toHaveTextContent("-$246,291");
    expect(table).toHaveTextContent("-$262,671");
    // Success shows the alternative's ABSOLUTE probability (winner 0.90 +
    // delta 0.02 = 0.92 → 92%), not the delta.
    expect(table).toHaveTextContent("92%");
  });

  it("results rows offer no run actions: reruns start from changing the inputs", async () => {
    const mockOptimize = optimize as jest.MockedFunction<typeof optimize>;
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
    mockGetRun.mockResolvedValue({
      run_id: "run-123",
      household_id: "hh-1",
      created_at: "2026-07-05 16:29:17.920023",
      result: resultWithAlternatives,
    });

    await act(async () => {
      renderPage();
    });
    await waitFor(() => screen.getByTestId("alternatives-table"));
    expect(screen.queryByTestId("run-policy-fill_22")).not.toBeInTheDocument();
    expect(screen.queryByText("Run this policy")).not.toBeInTheDocument();
    expect(mockOptimize).not.toHaveBeenCalled();
  });

  it("shows the forced-policy banner when the run was forced", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
    mockGetRun.mockResolvedValue({
      run_id: "run-123",
      household_id: "hh-1",
      created_at: "2026-07-05 16:29:17.920023",
      result: { ...resultWithAlternatives, forced_policy: "fill_22" },
    });

    await act(async () => {
      renderPage();
    });
    await waitFor(() => screen.getByTestId("results-title"));

    const banner = screen.getByTestId("forced-policy-banner");
    expect(banner).toHaveTextContent("Fill the 22% bracket");
    expect(banner).toHaveTextContent(/not the optimizer/i);
  });

  it("shows the plan nickname under the run and plan IDs", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
    mockGetRun.mockResolvedValue({
      run_id: "run-123",
      household_id: "hh-1",
      created_at: "2026-07-05 16:29:17.920023",
      result: minimalResult,
      inputs: { household: { nickname: "12%BracketBalanced" } } as never,
    });

    await act(async () => {
      renderPage();
    });
    await waitFor(() => screen.getByTestId("results-title"));

    expect(screen.getByTestId("plan-nickname")).toHaveTextContent(
      "Plan nickname: 12%BracketBalanced"
    );
  });

  it("omits the nickname line for a plan without one", async () => {
    mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
    mockGetRun.mockResolvedValue({
      run_id: "run-123",
      household_id: "hh-1",
      created_at: "2026-07-05 16:29:17.920023",
      result: minimalResult,
    });

    await act(async () => {
      renderPage();
    });
    await waitFor(() => screen.getByTestId("results-title"));

    expect(screen.queryByTestId("plan-nickname")).not.toBeInTheDocument();
  });

  describe("forced-policy banner names the optimizer's pick", () => {
    const forcedRun = (forced: string, pick: string) => ({
      run_id: "run-forced",
      household_id: "hh-1",
      created_at: "2026-07-05 16:29:17.920023",
      result: { ...resultWithAlternatives, forced_policy: forced, optimizer_pick: pick },
    });

    beforeEach(() => {
      mockGetHealth.mockResolvedValue({ status: "ok", llm: false });
      (listRuns as jest.Mock).mockResolvedValue([
        { run_id: "run-forced", created_at: "2026-07-06T00:00:00Z", duration_ms: 1, forced_policy: "fill_22" },
        { run_id: "run-optimized", created_at: "2026-07-05T00:00:00Z", duration_ms: 1, forced_policy: null },
      ]);
    });

    it("names a different pick and links back to the optimized run", async () => {
      mockGetRun.mockResolvedValue(forcedRun("fill_22", "none"));
      await act(async () => {
        renderPage();
      });
      await waitFor(() => screen.getByTestId("results-title"));

      const banner = screen.getByTestId("forced-policy-banner");
      expect(banner).toHaveTextContent("Fill the 22% bracket");
      expect(banner).toHaveTextContent(/optimizer.s own pick for these inputs is No conversions/i);
      await waitFor(() =>
        expect(screen.getByTestId("back-to-optimized-run")).toHaveAttribute(
          "href",
          "/results/run-optimized"
        )
      );
    });

    it("does not claim the pinned plan isn't the pick when it is", async () => {
      mockGetRun.mockResolvedValue(forcedRun("none", "none"));
      await act(async () => {
        renderPage();
      });
      await waitFor(() => screen.getByTestId("results-title"));

      const banner = screen.getByTestId("forced-policy-banner");
      expect(banner).toHaveTextContent(/also the optimizer.s own pick/i);
      expect(banner).not.toHaveTextContent(/not the optimizer/i);
    });
  });
});
