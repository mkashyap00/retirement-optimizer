import { getActiveOptimizeJob, optimize, submitOptimizeJob } from "@/lib/api";
import { isApiError } from "@/lib/apiError";
import type { ClaimSearchControls } from "@/lib/types";
import { saveJobMeta } from "@/lib/claimSetup";

export type StartResult =
  | { kind: "job"; jobId: string }
  | { kind: "run"; runId: string }
  | { kind: "busy"; jobId: string };

/** Start the run a setup describes for a SAVED plan: a background claim-age
 *  search when `controls` searches anyone, else the conversion optimizer.
 *  A running search is reported as `busy` -- never queued behind it, and
 *  never retried automatically. */
export async function startOptimization(opts: {
  householdId: string;
  nickname?: string | null;
  controls: ClaimSearchControls;
  monteCarloRuns?: number;
}): Promise<StartResult> {
  const searching = opts.controls.self.mode === "search" || opts.controls.spouse.mode === "search";
  if (!searching) {
    const { run_id } = await optimize(opts.householdId, opts.monteCarloRuns ?? 300);
    return { kind: "run", runId: run_id };
  }
  const active = await getActiveOptimizeJob().catch(() => null);
  if (active) return { kind: "busy", jobId: active.id };
  try {
    const { job_id } = await submitOptimizeJob(opts.householdId, opts.controls, opts.monteCarloRuns);
    saveJobMeta(job_id, {
      household_id: opts.householdId,
      nickname: opts.nickname ?? null,
      claim_search: opts.controls,
      started_at: new Date().toISOString(),
    });
    return { kind: "job", jobId: job_id };
  } catch (e) {
    if (isApiError(e, 409)) {
      const id = (e.detail as { job_id?: string } | null)?.job_id;
      if (id) return { kind: "busy", jobId: id };
    }
    throw e;
  }
}
