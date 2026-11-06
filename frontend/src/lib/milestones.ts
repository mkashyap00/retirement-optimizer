/** The years a reader looks for on a projection chart: salary ending, Social
 *  Security starting and RMDs beginning. Derived from the stored rows and
 *  the run's own inputs -- nothing is recomputed. */

import type { IncomeIn, YearRow } from "@/lib/types";

export interface Milestone {
  year: number;
  label: string;
}

export function milestones(
  rows: YearRow[],
  opts: {
    claimAges?: { self?: number | null; spouse?: number | null };
    /** Already receiving: no start to mark. */
    receiving?: { self?: boolean | null; spouse?: boolean | null };
    income?: IncomeIn[];
  },
): Milestone[] {
  if (rows.length === 0) return [];
  const first = rows[0].year;
  const last = rows[rows.length - 1].year;
  const out: Milestone[] = [];
  const who = (owner: string) => (owner === "spouse" ? "Spouse's" : owner === "joint" ? "Joint" : "Your");

  for (const inc of opts.income ?? []) {
    if (inc.category === "salary" && inc.end_year != null && inc.end_year >= first && inc.end_year < last) {
      out.push({ year: inc.end_year, label: `${who(inc.owner)} salary ends` });
    }
  }
  const claim = (person: "self" | "spouse", label: string) => {
    const age = opts.claimAges?.[person];
    if (age == null || opts.receiving?.[person]) return;
    const row = rows.find((r) => (person === "self" ? r.age_self : r.age_spouse) === age);
    // A first-year claim is a start only when the run says the person is not
    // already receiving; older runs without the flag may have been receiving.
    const firstOk = opts.receiving?.[person] === false;
    if (row && (row.year > first || (firstOk && row.year === first))) out.push({ year: row.year, label });
  };
  claim("self", "You claim Social Security");
  claim("spouse", "Spouse claims Social Security");
  const rmd = rows.find((r) => r.rmd > 0);
  if (rmd && rmd.year > first) out.push({ year: rmd.year, label: "RMDs begin" });

  // One entry per year, labels joined.
  const byYear = new Map<number, string[]>();
  out.forEach((m) => byYear.set(m.year, [...(byYear.get(m.year) ?? []), m.label]));
  return Array.from(byYear, ([year, labels]) => ({ year, label: labels.join(", ") }))
    .sort((a, b) => a.year - b.year);
}
