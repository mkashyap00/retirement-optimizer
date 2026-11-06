/**
 * @jest-environment jsdom
 */
import { startOptimization } from "../startRun";
import { getActiveOptimizeJob, optimize, submitOptimizeJob } from "../api";
import { ApiError } from "@/lib/apiError";

jest.mock("../api", () => ({
  getActiveOptimizeJob: jest.fn(),
  optimize: jest.fn(),
  submitOptimizeJob: jest.fn(),
}));

const SEARCH = { self: { mode: "search" as const }, spouse: { mode: "fixed" as const } };
const FIXED = { self: { mode: "fixed" as const }, spouse: { mode: "fixed" as const } };

beforeEach(() => jest.resetAllMocks());

test("fixed ages run the conversion optimizer directly", async () => {
  (optimize as jest.Mock).mockResolvedValue({ run_id: "r1" });
  expect(await startOptimization({ householdId: "hh", controls: FIXED })).toEqual({
    kind: "run", runId: "r1",
  });
  expect(submitOptimizeJob).not.toHaveBeenCalled();
});

test("a search starts a job and remembers how, for Run again", async () => {
  (getActiveOptimizeJob as jest.Mock).mockResolvedValue(null);
  (submitOptimizeJob as jest.Mock).mockResolvedValue({ job_id: "j1" });
  expect(await startOptimization({ householdId: "hh", nickname: "Plan", controls: SEARCH }))
    .toEqual({ kind: "job", jobId: "j1" });
  expect(JSON.parse(localStorage.getItem("optimize-job:j1")!)).toMatchObject({
    household_id: "hh", nickname: "Plan", claim_search: SEARCH,
  });
});

test("a running search is reported, never queued or retried", async () => {
  (getActiveOptimizeJob as jest.Mock).mockResolvedValue({ id: "other" });
  expect(await startOptimization({ householdId: "hh", controls: SEARCH })).toEqual({
    kind: "busy", jobId: "other",
  });
  expect(submitOptimizeJob).not.toHaveBeenCalled();

  (getActiveOptimizeJob as jest.Mock).mockResolvedValue(null);
  (submitOptimizeJob as jest.Mock).mockRejectedValue(
    new ApiError(409, '{"detail":{"message":"busy","job_id":"raced"}}')
  );
  expect(await startOptimization({ householdId: "hh", controls: SEARCH })).toEqual({
    kind: "busy", jobId: "raced",
  });
  expect(submitOptimizeJob).toHaveBeenCalledTimes(1);
});

test("a finished job's run is remembered after the job itself is forgotten", () => {
  const { recordJobRun, loadJobMeta, saveJobMeta } = jest.requireActual("../claimSetup");
  saveJobMeta("j9", { household_id: "hh", claim_search: SEARCH, started_at: "t" });
  recordJobRun("j9", "run-9");
  expect(loadJobMeta("j9").run_id).toBe("run-9");
});
