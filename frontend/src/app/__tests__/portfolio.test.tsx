/**
 * @jest-environment jsdom
 *
 * RTL tests for the holdings-only Portfolio page (src/app/portfolio/page.tsx).
 */

// --- Module mocks (hoisted before imports) ----------------------------------

jest.mock("@/lib/api", () => ({
  uploadPortfolio: jest.fn(),
  getPortfolio: jest.fn(),
}));

// --- Imports ----------------------------------------------------------------

import "@testing-library/jest-dom";
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from "@testing-library/react";
import { uploadPortfolio, getPortfolio } from "@/lib/api";
import PortfolioPage from "@/app/portfolio/page";

const MOCK_CSV =
  "symbol,shares,price,cost_basis,account_type\nVTI,500,285.10,95225,taxable\n";

const EMPTY_SUMMARY = { positions: [], uploaded_at: null, warnings: [] };

beforeEach(() => {
  jest.clearAllMocks();
  (getPortfolio as jest.Mock).mockResolvedValue(EMPTY_SUMMARY);
});

// --- Tests ------------------------------------------------------------------

describe("PortfolioPage — holdings management", () => {
  it("renders the file-upload button and template link, no Target Cash", async () => {
    await act(async () => {
      render(<PortfolioPage />);
    });
    expect(
      screen.getByRole("button", { name: /upload file/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /download template/i })
    ).toBeInTheDocument();
    // The Target Cash / sale-plan flow no longer lives here.
    expect(screen.queryByLabelText(/target cash/i)).not.toBeInTheDocument();
  });

  it("uploads pasted text and shows the lot count", async () => {
    (uploadPortfolio as jest.Mock).mockResolvedValue({ lots: 1, warnings: [] });

    await act(async () => {
      render(<PortfolioPage />);
    });

    fireEvent.change(screen.getByLabelText(/csv input/i), {
      target: { value: MOCK_CSV },
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /upload pasted text/i })
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("lot-count")).toHaveTextContent("1 lots");
    });
    // App-level upload: no household context passed.
    expect(uploadPortfolio).toHaveBeenCalledWith(MOCK_CSV);
  });

  it("shows an upload error on failure", async () => {
    (uploadPortfolio as jest.Mock).mockRejectedValue(
      new Error("HTTP 400: bad columns")
    );

    await act(async () => {
      render(<PortfolioPage />);
    });

    fireEvent.change(screen.getByLabelText(/csv input/i), {
      target: { value: "bad,csv\n" },
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /upload pasted text/i })
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/HTTP 400/)).toBeInTheDocument();
    });
  });

  it("renders the stored holdings table when positions exist", async () => {
    (getPortfolio as jest.Mock).mockResolvedValue({
      positions: [
        {
          ticker: "VTI",
          account_type: "taxable",
          shares: 500,
          price: 285.1,
          market_value: 142550,
          cost_basis: 95225,
          holding_period: "long_term",
        },
      ],
      uploaded_at: "2026-07-22T10:00:00",
      warnings: [],
    });

    await act(async () => {
      render(<PortfolioPage />);
    });

    await waitFor(() => {
      expect(screen.getByTestId("holdings-table")).toBeInTheDocument();
    });
    expect(screen.getByText("VTI")).toBeInTheDocument();
  });
});
