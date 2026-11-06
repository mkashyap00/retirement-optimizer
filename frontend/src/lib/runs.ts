import type { RunSummary } from "@/lib/types";
import { getRun, listRuns } from "@/lib/api";

/** The run a plan's "Results" should open: its newest OPTIMIZED run.
 *
 *  A "Run this policy" run is a what-if the user asked to see, not the
 *  optimizer's answer, so opening whichever run came last showed a pinned
 *  plan as if it were the result. Falls back to the newest run of any kind
 *  when every run was pinned (or the server predates `forced_policy`). */
export function latestOptimizedRun(runs: RunSummary[]): RunSummary | null {
  if (runs.length === 0) return null;
  const newestFirst = [...runs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  return newestFirst.find((r) => !r.forced_policy) ?? newestFirst[0];
}

/** The claim ages a plan's newest optimized run used (its recommendation),
 *  or null without one. A plan saved with a searched age and no comparison
 *  age has no stored age; this is the age it was run at, not an invented one. */
export async function recommendedClaimAges(
  householdId: string,
): Promise<{ self?: number | null; spouse?: number | null } | null> {
  const latest = latestOptimizedRun(await listRuns(householdId));
  if (!latest) return null;
  const run = await getRun(latest.run_id);
  return run.result?.claim_ages ?? null;
}
