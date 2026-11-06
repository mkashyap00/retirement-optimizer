/** Saved runs from before October 2026 explain a zero-conversion year as
 *  "either the conversion window is closed, or …", and blame any RMD year on
 *  the RMD filling the bracket even when room was left. The plan itself says
 *  which reason applies: this restates the year with it, the same rules as
 *  the backend's narrative.render_narrative. */

import type { YearRow } from "@/lib/types";

const LEGACY = /^No Roth conversion this year: either the conversion window is closed, or converting offered no lifetime after-tax benefit \(conversion strategies are always evaluated — see Alternative Policies\)\./;

// Old RMD wording; it stands only when the stored sizing shows no room left.
const LEGACY_RMD = /^No conversion this year: RMD of \$[\d,]+ plus other income already fills the \d+% bracket\./;

const THRU = /_thru_(\d{4})$/;

export function zeroConversionReason(row: YearRow, rows: YearRow[], policyId: string): string {
  if (policyId === "none") return "the recommended strategy makes no Roth conversions";
  const i = rows.indexOf(row);
  const before = i > 0 ? rows[i - 1].balance_traditional : null;
  if (before != null && before <= 1) return "nothing is left in traditional accounts to convert";
  const years = rows.filter((r) => r.conversion > 0).map((r) => r.year);
  if (years.length && row.year < years[0]) {
    return `the recommended strategy starts converting in ${years[0]}`;
  }
  const thru = THRU.exec(policyId);
  if (thru && row.year > Number(thru[1])) {
    return `the recommended strategy converts only through ${thru[1]}`;
  }
  if (years.length && row.year > years[years.length - 1]) {
    return `the recommended strategy's last conversion is in ${years[years.length - 1]}`;
  }
  return "the recommended strategy's rule found no room to convert this year";
}

function rmdFact(row: YearRow): string {
  const rmd = row.rationale?.withdrawal?.rmd_amount ?? 0;
  return rmd > 0
    ? ` This year's required minimum distribution is $${Math.round(rmd).toLocaleString("en-US")}.`
    : "";
}

function rmdFilledBracket(row: YearRow): boolean {
  const b = row.rationale?.bracket;
  return !!b && b.bracket_top != null && b.headroom_remaining <= 1;
}

/** The stored narrative, with the legacy either/or sentence, and an RMD
 *  sentence the sizing does not support, replaced. */
export function narrativeFor(row: YearRow, rows: YearRow[], policyId?: string): string {
  const text = row.rationale?.narrative ?? "";
  if (!policyId) return text;
  if (LEGACY.test(text)) {
    return text.replace(LEGACY, `No Roth conversion this year: ${zeroConversionReason(row, rows, policyId)}.`);
  }
  if (LEGACY_RMD.test(text) && !rmdFilledBracket(row)) {
    return text.replace(LEGACY_RMD,
      `No Roth conversion this year: ${zeroConversionReason(row, rows, policyId)}.${rmdFact(row)}`);
  }
  return text;
}
