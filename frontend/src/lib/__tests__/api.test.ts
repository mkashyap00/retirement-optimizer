import {
  createHousehold,
  listHouseholds,
  getHousehold,
  deleteHousehold,
  optimize,
  getRun,
  listRuns,
} from "../api";
import type { HouseholdPayload, OptimizationResult } from "../types";

// ---------------------------------------------------------------------------
// Mock global.fetch
// ---------------------------------------------------------------------------

const mockFetch = jest.fn();
global.fetch = mockFetch;

const BASE = "http://localhost:8000";

function mockOk(data: unknown, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  });
}

function mockErr(status: number, body = "Error") {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.reject(new Error("not json")),
    text: () => Promise.resolve(body),
  });
}

// 204 No Content: empty body — real fetch's res.json() rejects with a
// SyntaxError here, which is exactly the delete bug we regression-test.
function mockNoContent() {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status: 204,
    json: () => Promise.reject(new SyntaxError("Unexpected end of JSON input")),
    text: () => Promise.resolve(""),
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const minimalResult: OptimizationResult = {
  status: "success",
  computation_time_seconds: 0.42,
  paths_evaluated: 8,
  monte_carlo_runs: 300,
  winning_policy: {
    policy_id: "fill_22",
    lifetime_taxes_nominal: 200000,
    lifetime_taxes_pv: 150000,
    terminal_estate: 800000,
    success_probability: 0.91,
    score: 0.88,
    total_conversions: 60000,
    projected_future_marginal_rate: 0.24,
  },
  yearly_plan: [],
  alternative_policies: [],
  warnings: [],
};

const minimalPayload: HouseholdPayload = {
  household: {
    filing_status: "single",
    self_birth_date: "1960-01-15",
    state: "CA",
  },
  accounts: [
    { account_type: "traditional", owner: "self", balance: 500000 },
  ],
  income: [],
  settings: {
    required_spending: 80000,
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
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockFetch.mockClear();
});

// ── optimize ────────────────────────────────────────────────────────────────

describe("optimize", () => {
  it("POSTs to /optimize with correct URL and body, returns parsed result", async () => {
    mockOk({ run_id: "run-abc", result: minimalResult });

    const response = await optimize("hh-123", 100);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE}/optimize`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ household_id: "hh-123", monte_carlo_runs: 100 }),
      })
    );
    expect(response.run_id).toBe("run-abc");
    expect(response.result.winning_policy.policy_id).toBe("fill_22");
    expect(response.result.winning_policy.success_probability).toBe(0.91);
  });

  it("uses monte_carlo_runs=300 as default when omitted", async () => {
    mockOk({ run_id: "r", result: minimalResult });

    await optimize("hh-1");

    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE}/optimize`,
      expect.objectContaining({
        body: JSON.stringify({ household_id: "hh-1", monte_carlo_runs: 300 }),
      })
    );
  });

  it("throws Error containing status code on non-2xx", async () => {
    mockErr(404, "Household not found");

    await expect(optimize("missing-id")).rejects.toThrow("404");
  });

  it("throws Error containing response body text on non-2xx", async () => {
    mockErr(500, "Internal Server Error");

    await expect(optimize("x")).rejects.toThrow("Internal Server Error");
  });
});

// ── createHousehold ─────────────────────────────────────────────────────────

describe("createHousehold", () => {
  it("POSTs to /households and returns household_id", async () => {
    mockOk({ household_id: "hh-new" }, 201);

    const result = await createHousehold(minimalPayload);

    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE}/households`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(minimalPayload),
      })
    );
    expect(result.household_id).toBe("hh-new");
  });
});

// ── listHouseholds ───────────────────────────────────────────────────────────

describe("listHouseholds", () => {
  it("GETs /households and returns array of summaries", async () => {
    const summaries = [
      { household_id: "hh-1", filing_status: "single", state: "CA", created_at: "2026-01-01" },
    ];
    mockOk(summaries);

    const result = await listHouseholds();

    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE}/households`,
      expect.any(Object)
    );
    expect(result).toHaveLength(1);
    expect(result[0].household_id).toBe("hh-1");
  });
});

// ── getHousehold ─────────────────────────────────────────────────────────────

describe("getHousehold", () => {
  it("GETs /households/{id} and returns detail", async () => {
    mockOk({ household_id: "hh-1", household: {}, accounts: [], income: [], settings: {}, constraints: {} });

    const result = await getHousehold("hh-1");

    expect(mockFetch).toHaveBeenCalledWith(`${BASE}/households/hh-1`, expect.any(Object));
    expect(result.household_id).toBe("hh-1");
  });

  it("throws on 404", async () => {
    mockErr(404, "Household not found");

    await expect(getHousehold("bad")).rejects.toThrow("404");
  });
});

// ── deleteHousehold ───────────────────────────────────────────────────────────

describe("deleteHousehold", () => {
  it("DELETEs /households/{id} and resolves on 204 without parsing a body", async () => {
    mockNoContent();

    // Must NOT throw "Unexpected end of JSON input" on the empty 204 body.
    await expect(deleteHousehold("hh-1")).resolves.toBeUndefined();

    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE}/households/hh-1`,
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("throws on 404 (household already gone)", async () => {
    mockErr(404, "Household not found");

    await expect(deleteHousehold("bad")).rejects.toThrow("404");
  });
});

// ── getRun ────────────────────────────────────────────────────────────────────

describe("getRun", () => {
  it("GETs /runs/{run_id} and returns run detail", async () => {
    mockOk({
      run_id: "r1",
      household_id: "hh-1",
      created_at: "2026-01-01T00:00:00",
      result: minimalResult,
    });

    const result = await getRun("r1");

    expect(mockFetch).toHaveBeenCalledWith(`${BASE}/runs/r1`, expect.any(Object));
    expect(result.run_id).toBe("r1");
    expect(result.household_id).toBe("hh-1");
    expect(result.result.status).toBe("success");
  });
});

// ── listRuns ──────────────────────────────────────────────────────────────────

describe("listRuns", () => {
  it("GETs /households/{id}/runs and returns run summaries", async () => {
    const summaries = [
      { run_id: "r1", created_at: "2026-01-01T00:00:00", duration_ms: 500 },
    ];
    mockOk(summaries);

    const result = await listRuns("hh-1");

    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE}/households/hh-1/runs`,
      expect.any(Object)
    );
    expect(result).toHaveLength(1);
    expect(result[0].run_id).toBe("r1");
    expect(result[0].duration_ms).toBe(500);
  });
});
