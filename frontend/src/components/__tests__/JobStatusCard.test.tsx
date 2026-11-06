/**
 * @jest-environment jsdom
 */
import React from "react";
import "@testing-library/jest-dom";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { JobStatusCard, POLL_MS } from "../JobStatusCard";
import { getOptimizeJob } from "@/lib/api";
import { ApiError } from "@/lib/apiError";

jest.mock("@/lib/api", () => ({ getOptimizeJob: jest.fn() }));
jest.mock("next/link", () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

const job = (over: object) => ({
  id: "j1", household_id: "hh", status: "running", phase: "deterministic",
  progress: { done: 12, total: 48 }, run_id: null, error: null,
  created_at: new Date().toISOString(), started_at: new Date().toISOString(),
  finished_at: null, ...over,
});

async function flush(ms = 0) {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
}

beforeEach(() => {
  jest.resetAllMocks();
  jest.useFakeTimers();
});
afterEach(() => jest.useRealTimers());

test("shows the stage, its progress, elapsed time and that the page can be left", async () => {
  (getOptimizeJob as jest.Mock).mockResolvedValue(job({}));
  render(<JobStatusCard jobId="j1" title="Sample plan" />);
  await flush();
  expect(screen.getByText(/Sample plan — Optimizing/)).toBeInTheDocument();
  const stages = screen.getAllByRole("listitem");
  expect(stages.map((li) => li.getAttribute("data-state"))).toEqual(["current", "todo", "todo", "todo"]);
  expect(screen.getByTestId("job-stage-count")).toHaveTextContent("12 of 48 claim-age pairs");
  expect(screen.getByTestId("job-elapsed")).toHaveTextContent(/Elapsed: \d+ s/);
  expect(screen.getByText(/You can leave this page/)).toBeInTheDocument();
  expect(screen.getByTestId("job-announcement")).toHaveTextContent("Now: Compare strategies.");
});

test("a failed poll reconnects and keeps polling; it never starts anything", async () => {
  (getOptimizeJob as jest.Mock)
    .mockResolvedValueOnce(job({}))
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockResolvedValue(job({ phase: "monte_carlo", progress: { done: 5, total: 171 } }));
  const onRunAgain = jest.fn();
  render(<JobStatusCard jobId="j1" onRunAgain={onRunAgain} />);
  await flush();
  await flush(POLL_MS);
  // A failed connection cannot tell whether the server is still running.
  expect(screen.getByTestId("job-reconnecting")).toHaveTextContent(
    "Reconnecting… checking the search status."
  );
  await flush(POLL_MS * 2);
  expect(screen.queryByTestId("job-reconnecting")).toBeNull();
  expect(screen.getByText("Test market outcomes")).toBeInTheDocument();
  expect(onRunAgain).not.toHaveBeenCalled();
});

test("an unknown job is not called lost: check saved results before running again", async () => {
  // A restart forgets FINISHED jobs too, and their results are saved.
  (getOptimizeJob as jest.Mock).mockRejectedValue(new ApiError(404, "not found"));
  const onRunAgain = jest.fn();
  render(
    <JobStatusCard
      jobId="gone"
      onRunAgain={onRunAgain}
      savedResults={{ href: "/results/run-7", label: "View this plan's saved results" }}
    />
  );
  await flush();
  const msg = screen.getByTestId("job-error");
  expect(msg).toHaveTextContent(
    "This search's status is no longer available. Check saved results before running again."
  );
  expect(msg).not.toHaveTextContent(/could not be recovered|restarted while/);
  expect(screen.getByText("View this plan's saved results").closest("a")).toHaveAttribute(
    "href", "/results/run-7"
  );
  fireEvent.click(screen.getByTestId("job-run-again"));
  expect(onRunAgain).toHaveBeenCalledTimes(1);
  expect(screen.getByText("Back to dashboard")).toBeInTheDocument();
  expect(screen.getByTestId("job-announcement")).toHaveTextContent("no longer available");
});

test("'Prepare results' is a real stage while the run is saved", async () => {
  (getOptimizeJob as jest.Mock).mockResolvedValue(
    job({ phase: "prepare", progress: { done: 0, total: 1 } })
  );
  render(<JobStatusCard jobId="j1" />);
  await flush();
  const stages = screen.getAllByRole("listitem");
  expect(stages.map((li) => li.getAttribute("data-state"))).toEqual(["done", "done", "done", "current"]);
  expect(screen.getByTestId("job-announcement")).toHaveTextContent("Now: Prepare results.");
});

test("a shutdown-interrupted job reads as such; without inputs there is no Run again", async () => {
  (getOptimizeJob as jest.Mock).mockResolvedValue(
    job({ status: "failed", error: "interrupted: the server stopped" })
  );
  render(<JobStatusCard jobId="j1" />);
  await flush();
  expect(screen.getByTestId("job-error")).toHaveTextContent(/server was shut down/);
  expect(screen.queryByTestId("job-run-again")).toBeNull();
});

test("completion hands over the run and keeps a View results action", async () => {
  (getOptimizeJob as jest.Mock).mockResolvedValue(job({ status: "done", phase: "sensitivity", run_id: "run-9" }));
  const onDone = jest.fn();
  render(<JobStatusCard jobId="j1" onDone={onDone} />);
  await flush();
  expect(onDone).toHaveBeenCalledWith("run-9");
  expect(screen.getByText("View results").closest("a")).toHaveAttribute("href", "/results/run-9");
  expect(screen.getByTestId("job-announcement")).toHaveTextContent("Search complete");
});
