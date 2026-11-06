/** Each saved plan's claim-age choices (find the best age, or use an age I
 *  choose), kept in this browser. They decide which run a plan starts, but
 *  are not part of the saved plan; a plan saved and never run needs them to
 *  finish setup later. Absent when the plan was saved elsewhere or before
 *  they were recorded -- then Review asks rather than guessing. */

import type { ClaimModes } from "@/lib/claimSetup";

const PREFIX = "plan-claim-modes:";

export function savePlanModes(householdId: string, modes: ClaimModes): void {
  try {
    localStorage.setItem(PREFIX + householdId, JSON.stringify(modes));
  } catch {
    // storage blocked: Review will ask for them on resume
  }
}

export function loadPlanModes(householdId: string): ClaimModes | null {
  try {
    const raw = localStorage.getItem(PREFIX + householdId);
    const m = raw ? (JSON.parse(raw) as ClaimModes) : null;
    const ok = (v: unknown) => v === "search" || v === "fixed";
    return m && ok(m.self) && ok(m.spouse) ? m : null;
  } catch {
    return null;
  }
}
