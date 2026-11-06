/**
 * @jest-environment jsdom
 *
 * RTL tests for the dashboard page (src/app/page.tsx).
 */

// --- Module mocks (hoisted before imports) ----------------------------------

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/api", () => ({
  listHouseholds: jest.fn(),
  optimize: jest.fn(),
  listRuns: jest.fn(),
  deleteHousehold: jest.fn(),
  getActiveOptimizeJob: jest.fn().mockResolvedValue(null),
  getOptimizeJob: jest.fn(),
  submitOptimizeJob: jest.fn(),
  getHouseholdClaimAges: jest.fn(),
}));

// next/link renders a plain <a> in jsdom without the App Router context
jest.mock("next/link", () => {
  const MockLink = ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

// --- Imports ----------------------------------------------------------------

import React from "react";
import "@testing-library/jest-dom";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { useRouter } from "next/navigation";
import {
  listHouseholds,
  optimize,
  listRuns,
  deleteHousehold,
  getActiveOptimizeJob,
  getHouseholdClaimAges,
} from "@/lib/api";
import DashboardPage from "@/app/page";

// --- Browser-API polyfills --------------------------------------------------

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

// --- Helpers ----------------------------------------------------------------

const mockPush = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  (getActiveOptimizeJob as jest.Mock).mockResolvedValue(null);
  (listRuns as jest.Mock).mockResolvedValue([]);
});

// --- Tests ------------------------------------------------------------------

describe("DashboardPage — empty state", () => {
  it("renders the New Plan CTA when there are no households", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([]);

    await act(async () => {
      render(<DashboardPage />);
    });

    // The CTA card copy
    expect(screen.getByText("No plans yet")).toBeInTheDocument();
    // There should be at least one link/button going to /wizard
    const wizardLinks = screen.getAllByRole("link", { name: /new plan/i });
    expect(wizardLinks.length).toBeGreaterThan(0);
    expect(wizardLinks[0]).toHaveAttribute("href", "/wizard");
  });

  it("always shows a New Plan header button", async () => {
    (listHouseholds as jest.Mock).mockResolvedValue([]);

    await act(async () => {
      render(<DashboardPage />);
    });

    // Header "New Plan" button is always rendered regardless of list state
    const links = screen.getAllByRole("link", { name: /new plan/i });
    expect(links.length).toBeGreaterThanOrEqual(1);
  });
});

describe("DashboardPage — with households", () => {
  const mockHousehold = {
    household_id: "hh-123",
    filing_status: "joint",
    state: "CA",
    // Backend format: space-separated, microseconds, no timezone (treated as local)
    created_at: "2026-07-05 16:29:17.920023",
    nickname: null,
  };

  beforeEach(() => {
    (listHouseholds as jest.Mock).mockResolvedValue([mockHousehold]);
  });

  it("renders a household card with state and filing status", async () => {
    (listRuns as jest.Mock).mockResolvedValue([]);
    await act(async () => {
      render(<DashboardPage />);
    });

    expect(screen.getByText("CA")).toBeInTheDocument();
    expect(screen.getByText("Married filing jointly")).toBeInTheDocument();
  });

  it("shows the latest completed run and its type instead of the creation date", async () => {
    (listRuns as jest.Mock).mockResolvedValue([
      { run_id: "run-1", created_at: "2026-07-05 16:29:17.920023", duration_ms: 1,
        forced_policy: null, claim_search: true },
    ]);
    await act(async () => {
      render(<DashboardPage />);
    });

    const desc = await screen.findByTestId("plan-latest-run");
    await waitFor(() => expect(desc.textContent).toContain("Jul 5, 2026"));
    expect(desc.textContent).toContain("Conversions + claim ages");
  });

  it("'View results' opens the newest existing run without re-optimizing", async () => {
    (listRuns as jest.Mock).mockResolvedValue([
      { run_id: "run-old", created_at: "2026-03-01T00:00:00Z", duration_ms: 100 },
      { run_id: "run-new", created_at: "2026-06-01T00:00:00Z", duration_ms: 120 },
    ]);

    await act(async () => {
      render(<DashboardPage />);
    });

    const btn = screen.getByTestId("view-results");
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    expect(mockPush).toHaveBeenCalledWith("/results/run-new");
    expect(optimize).not.toHaveBeenCalled();
  });

  it("'View results' opens the newest OPTIMIZED run, not a newer pinned one", async () => {
    // A "Run this policy" run is a what-if the user asked to see; the plan's
    // result is the latest run the optimizer actually chose.
    (listRuns as jest.Mock).mockResolvedValue([
      { run_id: "run-pinned", created_at: "2026-06-02T00:00:00Z", duration_ms: 1, forced_policy: "fill_10_annual" },
      { run_id: "run-optimized", created_at: "2026-06-01T00:00:00Z", duration_ms: 1, forced_policy: null },
    ]);

    await act(async () => {
      render(<DashboardPage />);
    });
    const btn = screen.getByTestId("view-results");
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    expect(mockPush).toHaveBeenCalledWith("/results/run-optimized");
  });

  it("'View results' falls back to the newest run when every run was pinned", async () => {
    (listRuns as jest.Mock).mockResolvedValue([
      { run_id: "run-a", created_at: "2026-06-01T00:00:00Z", duration_ms: 1, forced_policy: "none" },
      { run_id: "run-b", created_at: "2026-06-02T00:00:00Z", duration_ms: 1, forced_policy: "fill_22" },
    ]);

    await act(async () => {
      render(<DashboardPage />);
    });
    const btn = screen.getByTestId("view-results");
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    expect(mockPush).toHaveBeenCalledWith("/results/run-b");
  });

  it("a plan saved but never run offers Finish setup and run, reopening Review for that plan", async () => {
    (listRuns as jest.Mock).mockResolvedValue([]);

    await act(async () => {
      render(<DashboardPage />);
    });

    expect(await screen.findByTestId("plan-unfinished")).toHaveTextContent("no run has completed");
    expect(screen.queryByTestId("view-results")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("finish-setup"));
    expect(mockPush).toHaveBeenCalledWith("/wizard?resume=hh-123");
    // Nothing starts from the dashboard itself.
    expect(optimize).not.toHaveBeenCalled();
  });

  it("a plan whose runs could not be listed is not called unfinished", async () => {
    (listRuns as jest.Mock).mockRejectedValue(new Error("HTTP 500"));
    await act(async () => {
      render(<DashboardPage />);
    });
    expect(screen.getByTestId("view-results")).toBeDisabled();
    expect(screen.queryByTestId("finish-setup")).not.toBeInTheDocument();
  });

  it("says when a plan's runs could not be loaded, and Try again reloads them", async () => {
    (listRuns as jest.Mock).mockRejectedValueOnce(new Error("HTTP 500")).mockResolvedValue([
      { run_id: "r1", created_at: "2026-10-01T10:00:00", status: "optimal", claim_search: false },
    ]);
    await act(async () => {
      render(<DashboardPage />);
    });
    expect(screen.getByTestId("plan-runs-failed")).toHaveTextContent("Could not load this plan's runs");
    expect(screen.getByTestId("plan-latest-run")).toHaveTextContent("Latest run unavailable");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    });
    expect(screen.queryByTestId("plan-runs-failed")).not.toBeInTheDocument();
    expect(screen.getByTestId("view-results")).toBeEnabled();
  });

  it("a plan with a search running offers View progress", async () => {
    (listRuns as jest.Mock).mockResolvedValue([]);
    (getActiveOptimizeJob as jest.Mock).mockResolvedValue({ id: "job-9", household_id: "hh-123" });
    await act(async () => {
      render(<DashboardPage />);
    });
    fireEvent.click(await screen.findByTestId("view-progress"));
    expect(mockPush).toHaveBeenCalledWith("/jobs/job-9");
    expect(screen.queryByTestId("finish-setup")).not.toBeInTheDocument();
  });

  it("a card offers only View results and Delete: no run setup, no Portfolio", async () => {
    (listRuns as jest.Mock).mockResolvedValue([]);

    await act(async () => {
      render(<DashboardPage />);
    });

    // Choosing what to optimize happens in the wizard; changing inputs is a
    // What-if. The holdings are shared, so Portfolio is in the top bar only.
    expect(screen.queryByTestId("run-new-optimization")).not.toBeInTheDocument();
    expect(screen.queryByTestId("plan-menu")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Portfolio" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete plan" })).toBeInTheDocument();
    expect(getHouseholdClaimAges).not.toHaveBeenCalled();
  });

  it("renders nickname as card title when nickname is set", async () => {
    (listRuns as jest.Mock).mockResolvedValue([]);
    const householdWithNick = { ...mockHousehold, nickname: "Retire at 65" };
    (listHouseholds as jest.Mock).mockResolvedValue([householdWithNick]);

    await act(async () => {
      render(<DashboardPage />);
    });

    expect(screen.getByText("Retire at 65")).toBeInTheDocument();
    // State still visible in the description
    expect(screen.getByTestId("plan-latest-run")).toHaveTextContent(/^CA ·/);
  });

  it("deletes a household after confirmation and removes its card", async () => {
    (deleteHousehold as jest.Mock).mockResolvedValue(undefined);
    const confirmSpy = jest
      .spyOn(window, "confirm")
      .mockReturnValue(true);

    await act(async () => {
      render(<DashboardPage />);
    });

    // Card is present
    expect(screen.getByText("CA")).toBeInTheDocument();

    // A labelled trash icon, behind the existing confirmation.
    const deleteBtn = screen.getByRole("button", { name: "Delete plan" });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalled();
      expect(deleteHousehold).toHaveBeenCalledWith("hh-123");
      // Card removed from the list
      expect(screen.queryByText("CA")).not.toBeInTheDocument();
    });

    confirmSpy.mockRestore();
  });

  it("does not delete when the confirmation is dismissed", async () => {
    const confirmSpy = jest
      .spyOn(window, "confirm")
      .mockReturnValue(false);

    await act(async () => {
      render(<DashboardPage />);
    });

    const deleteBtn = screen.getByRole("button", { name: "Delete plan" });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    expect(deleteHousehold).not.toHaveBeenCalled();
    // Card still present
    expect(screen.getByText("CA")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// DashboardPage — backend-down state (issue #1)
// ---------------------------------------------------------------------------

describe("DashboardPage — backend-down state", () => {
  it("renders a friendly card when fetch throws TypeError (network failure)", async () => {
    (listHouseholds as jest.Mock).mockRejectedValue(
      new TypeError("Failed to fetch")
    );

    await act(async () => {
      render(<DashboardPage />);
    });

    await waitFor(() => {
      expect(
        screen.getByText(/can't reach the optimizer service/i)
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /retry/i })
      ).toBeInTheDocument();
    });
  });

  it("Retry button triggers a second fetch attempt", async () => {
    (listHouseholds as jest.Mock)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce([]);

    await act(async () => {
      render(<DashboardPage />);
    });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /retry/i })
      ).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    });

    await waitFor(() => {
      expect(listHouseholds).toHaveBeenCalledTimes(2);
    });
  });
});
