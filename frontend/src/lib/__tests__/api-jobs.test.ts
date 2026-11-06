import { optimize, submitOptimizeJob, getOptimizeJob, getActiveOptimizeJob } from "../api";

const mockFetch = jest.fn();
global.fetch = mockFetch;

function mockOk(data: unknown, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  });
}

function body(call = 0) {
  return JSON.parse(mockFetch.mock.calls[call][1].body);
}

beforeEach(() => mockFetch.mockReset());

test("optimize sends pinned claim ages only when given", async () => {
  mockOk({ run_id: "r" });
  await optimize("hh", 300, "fill_22", { self: 70, spouse: 67 });
  expect(body()).toEqual({
    household_id: "hh", monte_carlo_runs: 300, policy_id: "fill_22",
    ss_claim_age_self: 70, ss_claim_age_spouse: 67,
  });
  mockOk({ run_id: "r" });
  await optimize("hh", 300, "fill_22", { self: 70, spouse: null });
  expect(body(1)).toEqual({
    household_id: "hh", monte_carlo_runs: 300, policy_id: "fill_22", ss_claim_age_self: 70,
  });
});

test("submitOptimizeJob posts the claim controls", async () => {
  mockOk({ job_id: "j1", status: "queued" }, 202);
  const r = await submitOptimizeJob("hh", { self: { mode: "search" }, spouse: { mode: "fixed" } });
  expect(r.job_id).toBe("j1");
  expect(mockFetch.mock.calls[0][0]).toBe("http://localhost:8000/optimize/jobs");
  expect(body()).toEqual({
    household_id: "hh", monte_carlo_runs: 300,
    claim_search: { self: { mode: "search" }, spouse: { mode: "fixed" } },
  });
});

test("job status and active job are GETs", async () => {
  mockOk({ id: "j1" });
  await getOptimizeJob("j1");
  expect(mockFetch.mock.calls[0][0]).toBe("http://localhost:8000/optimize/jobs/j1");
  mockOk(null);
  expect(await getActiveOptimizeJob()).toBeNull();
  expect(mockFetch.mock.calls[1][0]).toBe("http://localhost:8000/optimize/jobs/active");
});
