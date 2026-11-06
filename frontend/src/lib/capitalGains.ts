import type { CapitalGainsIn } from "@/lib/types";

/** This year's blank entry: nothing realized, nothing carried in. */
export function noCapitalGains(): CapitalGainsIn {
  return {
    tax_year: new Date().getFullYear(),
    short_term: 0,
    long_term: 0,
    carryover_short_term: 0,
    carryover_long_term: 0,
  };
}

/** True when any figure is entered. */
export function hasCapitalGains(g: CapitalGainsIn | null | undefined): g is CapitalGainsIn {
  return !!g && [g.short_term, g.long_term, g.carryover_short_term, g.carryover_long_term]
    .some((v) => (v ?? 0) !== 0);
}

/** What is saved: the entered figures, or null when none are entered. */
export function capitalGainsPayload(g: CapitalGainsIn | null | undefined): CapitalGainsIn | null {
  if (!hasCapitalGains(g)) return null;
  return {
    // Kept as entered: a draft carried past New Year must not relabel last
    // year's gains as this year's (the run then reports them as not applied).
    tax_year: g.tax_year ?? new Date().getFullYear(),
    short_term: g.short_term ?? 0,
    long_term: g.long_term ?? 0,
    carryover_short_term: g.carryover_short_term ?? 0,
    carryover_long_term: g.carryover_long_term ?? 0,
  };
}

const dollars = (v: number) =>
  `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

/** One line per entry, for Review and the run's inputs: label and value. */
export function capitalGainsLines(g: CapitalGainsIn | null | undefined): [string, string][] {
  if (!hasCapitalGains(g)) return [];
  const lines: [string, string][] = [
    [`Gains realized in ${g.tax_year} (− = loss)`,
      `short-term ${dollars(g.short_term ?? 0)} · long-term ${dollars(g.long_term ?? 0)}`],
  ];
  if ((g.carryover_short_term ?? 0) || (g.carryover_long_term ?? 0))
    lines.push([`Loss carried into ${g.tax_year}`,
      `short-term ${dollars(g.carryover_short_term ?? 0)} · long-term ${dollars(g.carryover_long_term ?? 0)}`]);
  return lines;
}
