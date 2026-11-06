/** Claim-age run setup: what a search would compare, before anything runs.
 *
 *  The eligibility itself comes from the backend (POST /claim-ages/preview,
 *  GET /households/{id}/claim-ages), the same rules the search applies; this
 *  module only turns it plus the user's per-person choice into the run that
 *  will happen and the words that describe it. */

import type { ClaimSearchControls } from "@/lib/types";

export type PersonKey = "self" | "spouse";
export type ClaimMode = "search" | "fixed";
export type ClaimModes = Record<PersonKey, ClaimMode>;

export interface PersonPreview {
  status: "searchable" | "receiving" | "assumed_70" | "no_benefit" | "needs_answer" | "invalid";
  age: number;
  entered_age: number | null;
  receiving: boolean | null;
  pia: number | null;
  ages: number[];
  exclusions: { age: number; reason: string }[];
  message: string | null;
}

export interface ClaimPreview {
  self: PersonPreview | null;
  spouse: PersonPreview | null;
  /** A saved plan whose stored inputs a run would refuse. */
  error?: string;
}

export const DEFAULT_CLAIM_MODES: ClaimModes = { self: "search", spouse: "search" };

/** Measured on a salaried couple's plan: ~4 s per claim pair (deterministic search,
 *  Monte Carlo and sensitivity together), plus a fixed part. */
const SECONDS_PER_PAIR = 4;
const FIXED_SECONDS = 15;

export const PERSON_LABEL: Record<PersonKey, string> = { self: "You", spouse: "Spouse" };

/** Whether this person's age is actually searched: chosen AND searchable. */
export function isSearched(p: PersonPreview | null, mode: ClaimMode): boolean {
  return p != null && p.status === "searchable" && mode === "search" && p.ages.length > 1;
}

/** Problems that must be fixed before any run (fixed or searched). */
export function blockingProblems(preview: ClaimPreview | null): string[] {
  if (!preview) return [];
  if (preview.error) return [preview.error];
  const out: string[] = [];
  (["self", "spouse"] as const).forEach((k) => {
    const p = preview[k];
    if (p && (p.status === "invalid" || p.status === "needs_answer") && p.message) {
      out.push(`${PERSON_LABEL[k]}: ${p.message}`);
    }
  });
  return out;
}

/** Everything that stops THIS setup from running: input problems, plus a
 *  person held at their chosen age while the other is searched when that age
 *  is one the search skips -- every pair would then include it, none would be
 *  eligible, and the server would refuse the search after the plan was saved.
 *  (With both ages fixed there is no search, and any age can be modelled.) */
export function runProblems(preview: ClaimPreview | null, modes: ClaimModes): string[] {
  const out = blockingProblems(preview);
  if (!preview || out.length > 0) return out;
  // Held at "an age I choose" with none chosen: the run would have no age to
  // model, so it would drop that benefit. The server refuses it too.
  (["self", "spouse"] as const).forEach((k) => {
    const p = preview[k];
    if (p && p.status === "searchable" && !isSearched(p, modes[k]) && p.entered_age == null) {
      out.push(`${PERSON_LABEL[k]}: choose a claim age, or let the optimizer find the best one.`);
    }
  });
  if (out.length > 0) return out;
  const searching = (["self", "spouse"] as const).some((k) => isSearched(preview[k], modes[k]));
  if (!searching) return out;
  (["self", "spouse"] as const).forEach((k) => {
    const p = preview[k];
    if (!p || p.status !== "searchable" || isSearched(p, modes[k]) || p.entered_age == null) return;
    if (p.ages.includes(p.entered_age)) return;
    const why = p.exclusions.find((e) => e.age === p.entered_age)?.reason;
    out.push(
      `${PERSON_LABEL[k]}: the chosen age ${p.entered_age} is skipped by the search` +
        `${why ? ` (${why})` : ""}. Let the optimizer search this age too, choose an eligible ` +
        `age (${range(p.ages)}), or hold both ages fixed.`
    );
  });
  return out;
}

function range(ages: number[]): string {
  if (ages.length === 0) return "none";
  const lo = Math.min(...ages);
  const hi = Math.max(...ages);
  return lo === hi ? `age ${lo}` : `ages ${lo}–${hi}`;
}

export interface SearchSummary {
  /** True when at least one person's claim age is searched. */
  searching: boolean;
  pairs: number;
  /** "Compare 48 claim-age combinations" or "Social Security ages held fixed: …". */
  headline: string;
  /** One line per person. */
  people: string[];
  /** Why ages are skipped, when any are. */
  exclusionNote: string | null;
  /** "Compare against your entered ages: 69 and 67.", or that there is no
   *  comparison because a searched age has no comparison age. */
  comparison: string | null;
  estimate: string;
  actionLabel: string;
}

export function searchSummary(preview: ClaimPreview | null, modes: ClaimModes): SearchSummary {
  const people: string[] = [];
  let pairs = 1;
  let searching = false;
  let anyExcluded = false;
  const entered: string[] = [];
  let missingComparison = false;
  (["self", "spouse"] as const).forEach((k) => {
    const p = preview?.[k];
    if (!p) return;
    const label = PERSON_LABEL[k];
    if (p.entered_age != null) entered.push(String(p.entered_age));
    else if (p.status !== "no_benefit") missingComparison = true;
    if (isSearched(p, modes[k])) {
      searching = true;
      pairs *= p.ages.length;
      people.push(
        `${label}: searching ${range(p.ages)}` +
          (p.entered_age != null ? ` (compared with ${p.entered_age})` : ""),
      );
      if (p.exclusions.length > 0) anyExcluded = true;
    } else if (p.status === "receiving") {
      people.push(`${label}: ${p.entered_age} (already receiving — fixed)`);
    } else if (p.status === "assumed_70") {
      people.push(`${label}: 70 (over 70, not yet filed — modelled as filing now)`);
    } else if (p.status === "no_benefit") {
      people.push(`${label}: no Social Security benefit entered`);
    } else if (p.entered_age != null) {
      people.push(`${label}: ${p.entered_age} (your chosen age)`);
    }
  });
  const seconds = FIXED_SECONDS + SECONDS_PER_PAIR * pairs;
  const minutes = Math.max(1, Math.round(seconds / 60));
  return {
    searching,
    pairs: searching ? pairs : 1,
    headline: searching
      ? `Compare ${pairs} claim-age combination${pairs === 1 ? "" : "s"}`
      : "Social Security ages held fixed",
    people,
    exclusionNote: anyExcluded
      ? "Earlier ages are skipped because a salary is paid before full retirement age. " +
        "This model does not apply Social Security's earnings test, so it leaves those " +
        "ages out of the search — claiming then is not prohibited."
      : null,
    // The backend builds the "your ages" comparison only when every person
    // has an age (claiming.enumerate_scenarios); it never invents one.
    comparison: !searching
      ? null
      : missingComparison
        ? "No comparison age entered for everyone, so the results show the recommended " +
          "ages without a comparison with ages of your own."
        : `Compare against your entered age${entered.length > 1 ? "s" : ""}: ${entered.join(" and ")}.`,
    estimate: searching ? `About ${minutes} minute${minutes === 1 ? "" : "s"}` : "Under a minute",
    actionLabel: searching ? "Optimize conversions and claim ages" : "Optimize conversions",
  };
}

/** The job body for the chosen modes. A person who cannot be searched is fixed. */
export function controlsFor(preview: ClaimPreview | null, modes: ClaimModes): ClaimSearchControls {
  return {
    self: { mode: isSearched(preview?.self ?? null, modes.self) ? "search" : "fixed" },
    spouse: { mode: isSearched(preview?.spouse ?? null, modes.spouse) ? "search" : "fixed" },
  };
}

// ---------------------------------------------------------------------------
// What a job was started with, so its page can offer "Run again" after an
// interruption (jobs live in server memory; this lives in the browser).
// ---------------------------------------------------------------------------

export interface JobMeta {
  household_id: string;
  nickname?: string | null;
  claim_search: ClaimSearchControls;
  started_at: string;
  /** Set once the page sees the job finish: the result outlives the job. */
  run_id?: string;
}

const META_PREFIX = "optimize-job:";

export function saveJobMeta(jobId: string, meta: JobMeta): void {
  try {
    localStorage.setItem(META_PREFIX + jobId, JSON.stringify(meta));
  } catch {
    // storage blocked: "Run again" falls back to the dashboard
  }
}

/** Record a finished job's run, so its link survives the job being forgotten. */
export function recordJobRun(jobId: string, runId: string): void {
  const meta = loadJobMeta(jobId);
  if (meta && meta.run_id !== runId) saveJobMeta(jobId, { ...meta, run_id: runId });
}

export function loadJobMeta(jobId: string): JobMeta | null {
  try {
    const raw = localStorage.getItem(META_PREFIX + jobId);
    return raw ? (JSON.parse(raw) as JobMeta) : null;
  } catch {
    return null;
  }
}
