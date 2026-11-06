import { ApiError } from "./apiError";
import type { ClaimPreview } from "./claimSetup";
import type {
  HouseholdPayload,
  HouseholdSummary,
  HouseholdDetail,
  OptimizationResult,
  OptimizeJob,
  ClaimSearchControls,
  RunDetail,
  RunSummary,
  CompareConstraints,
  CompareOverrides,
  CompareResult,
  HealthResponse,
  NarrativeResponse,
  PortfolioUploadResponse,
  SalePlanResponse,
  PortfolioSummary,
} from "./types";

export const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Internal fetch helper — centralises error handling and JSON parsing
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }

  // No-content responses (e.g. 204 from DELETE) have an empty body — calling
  // res.json() on them throws "Unexpected end of JSON input".
  if (res.status === 204 || res.status === 205) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Household endpoints
// ---------------------------------------------------------------------------

/** POST /households → 201 {household_id} */
export function createHousehold(
  p: HouseholdPayload
): Promise<{ household_id: string }> {
  return apiFetch("/households", {
    method: "POST",
    body: JSON.stringify(p),
  });
}

/** PUT /households/{id} → replace a saved plan's inputs (its runs are kept) */
export function updateHousehold(id: string, p: HouseholdPayload): Promise<unknown> {
  return apiFetch(`/households/${id}`, {
    method: "PUT",
    body: JSON.stringify(p),
  });
}

/** GET /households → list of lightweight summaries */
export function listHouseholds(): Promise<HouseholdSummary[]> {
  return apiFetch("/households");
}

/** GET /households/{id} → full nested payload */
export function getHousehold(id: string): Promise<HouseholdDetail> {
  return apiFetch(`/households/${id}`);
}

/** DELETE /households/{id} → 204 */
export function deleteHousehold(id: string): Promise<void> {
  return apiFetch(`/households/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Optimization endpoints
// ---------------------------------------------------------------------------

/** POST /optimize → {run_id, result}. policy_id forces a specific policy;
 *  claimAges runs at those ages instead of the stored ones (null = stored). */
export function optimize(
  household_id: string,
  monte_carlo_runs = 300,
  policy_id?: string,
  claimAges?: { self?: number | null; spouse?: number | null }
): Promise<{ run_id: string; result: OptimizationResult }> {
  return apiFetch("/optimize", {
    method: "POST",
    body: JSON.stringify({
      household_id,
      monte_carlo_runs,
      ...(policy_id ? { policy_id } : {}),
      ...(claimAges?.self != null ? { ss_claim_age_self: claimAges.self } : {}),
      ...(claimAges?.spouse != null ? { ss_claim_age_spouse: claimAges.spouse } : {}),
    }),
  });
}

/** POST /optimize/jobs → 202 {job_id}: a background joint claim-age search.
 *  409 while another job runs; 422 for claim inputs it cannot search. */
export function submitOptimizeJob(
  household_id: string,
  claim_search: ClaimSearchControls,
  monte_carlo_runs = 300
): Promise<{ job_id: string; status: string }> {
  return apiFetch("/optimize/jobs", {
    method: "POST",
    body: JSON.stringify({ household_id, monte_carlo_runs, claim_search }),
  });
}

/** GET /optimize/jobs/{id}. 404 = unknown, including any job from before a
 *  server restart (jobs live in memory). */
export function getOptimizeJob(job_id: string): Promise<OptimizeJob> {
  return apiFetch(`/optimize/jobs/${job_id}`);
}

/** POST /claim-ages/preview → per person, what a claim-age search would try
 *  for an UNSAVED plan (the wizard). Same rules the search applies. */
export function previewClaimAges(body: {
  household: HouseholdPayload["household"];
  income: HouseholdPayload["income"];
  ss_pia_self?: number | null;
  ss_claim_age_self?: number | null;
  ss_receiving_self?: boolean | null;
  ss_pia_spouse?: number | null;
  ss_claim_age_spouse?: number | null;
  ss_receiving_spouse?: boolean | null;
}): Promise<ClaimPreview> {
  return apiFetch("/claim-ages/preview", { method: "POST", body: JSON.stringify(body) });
}

/** GET /households/{id}/claim-ages → the same preview for a saved plan. */
export function getHouseholdClaimAges(household_id: string): Promise<ClaimPreview> {
  return apiFetch(`/households/${household_id}/claim-ages`);
}

/** GET /optimize/jobs/active → the queued/running job, or null. */
export function getActiveOptimizeJob(): Promise<OptimizeJob | null> {
  return apiFetch("/optimize/jobs/active");
}

/** GET /runs/{run_id} → {run_id, household_id, created_at, result} */
export function getRun(run_id: string): Promise<RunDetail> {
  return apiFetch(`/runs/${run_id}`);
}

/** GET /households/{household_id}/runs → list of run summaries */
export function listRuns(household_id: string): Promise<RunSummary[]> {
  return apiFetch(`/households/${household_id}/runs`);
}

// ---------------------------------------------------------------------------
// Health + LLM narrative endpoints
// ---------------------------------------------------------------------------

/** GET /health → {status, llm} */
export function getHealth(): Promise<HealthResponse> {
  return apiFetch("/health");
}

/** POST /runs/{run_id}/narrative → {narrative} */
export function generateNarrative(run_id: string): Promise<NarrativeResponse> {
  return apiFetch(`/runs/${run_id}/narrative`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Compare endpoint
// ---------------------------------------------------------------------------

/** POST /compare → {result_a, result_b, difference} */
/** Conversion strategies actually available for this household's inputs.
 *
 *  Which policies exist depends on the inputs, not on a fixed menu: a rule
 *  that never finds room is not generated, the `_thru_<YYYY>` years depend on
 *  the household, and the conversion window / IRMAA / bracket-cap settings
 *  prune others. Offering the full list lets a user pick something that 400s. */
export function listPolicies(household_id: string): Promise<{ policies: string[] }> {
  return apiFetch(`/households/${household_id}/policies`);
}

/** POST /households/{id}/policies → strategies ONE what-if scenario can run:
 *  the stored plan with that scenario's constraints and overrides applied. */
export function listScenarioPolicies(
  household_id: string,
  constraints: CompareConstraints,
  overrides: CompareOverrides
): Promise<{ policies: string[] }> {
  return apiFetch(`/households/${household_id}/policies`, {
    method: "POST",
    body: JSON.stringify({ constraints, overrides }),
  });
}

export function compareScenarios(
  household_id: string,
  constraints_a: CompareConstraints,
  constraints_b: CompareConstraints,
  overrides_a: CompareOverrides = {},
  overrides_b: CompareOverrides = {},
  // Match the Results page (/optimize uses 300) so an unchanged scenario
  // reproduces the baseline winner instead of flipping on a near-tie.
  monte_carlo_runs = 300
): Promise<CompareResult> {
  return apiFetch("/compare", {
    method: "POST",
    body: JSON.stringify({
      household_id,
      constraints_a,
      constraints_b,
      overrides_a,
      overrides_b,
      monte_carlo_runs,
    }),
  });
}

// ---------------------------------------------------------------------------
// Portfolio endpoints
// ---------------------------------------------------------------------------

/** POST /portfolio → {lots, warnings}. The portfolio is app-level (default
 * profile), not per household. Pass householdId to reconcile against a plan. */
export function uploadPortfolio(
  csv: string,
  householdId?: string
): Promise<PortfolioUploadResponse> {
  const q = householdId ? `?household_id=${householdId}` : "";
  return apiFetch(`/portfolio${q}`, {
    method: "POST",
    body: JSON.stringify({ csv }),
  });
}

/** GET /portfolio/sale-plan?target_cash=N → SalePlan */
export function getSalePlan(targetCash: number): Promise<SalePlanResponse> {
  return apiFetch(`/portfolio/sale-plan?target_cash=${targetCash}`);
}

/** GET /portfolio → stored holdings summary for the default profile */
export function getPortfolio(): Promise<PortfolioSummary> {
  return apiFetch(`/portfolio`);
}
