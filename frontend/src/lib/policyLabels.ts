/** Names for optimizer policy ids, and the strategies a picker can offer.
 *
 * Plain data and string functions, shared by the results table, the result
 * summary and the What-if page (backend src/reports/policy_labels.py names
 * them the same way in the exports). */

/** Human-readable names for optimizer policy ids.
 *
 * "Every year" policies apply the same bracket-fill rule every year until the
 * IRA is exhausted. Limited-duration rules (`fill_22_thru_2031`) apply the rule
 * through that year, then stop, and level-dollar rules (`level_5pct_annual`,
 * `level_5pct_thru_2029`) convert a fixed share of the starting IRA; their
 * years depend on the household, so `policyLabel` names them from the id. */
export const POLICY_LABELS: Record<string, string> = {
  none: "No conversions",
  // Consistent-rule policies: fill the bracket EVERY year across the full horizon.
  fill_10_annual: "Fill the 10% bracket every year",
  fill_12_annual: "Fill the 12% bracket every year",
  fill_22_annual: "Fill the 22% bracket every year",
  fill_24_annual: "Fill the 24% bracket every year",
  fill_32_annual: "Fill the 32% bracket every year",
};

/** Greedy-rollout policies, removed from the search in October 2026: a named
 *  move in year 1, then each of the next ~5 years re-optimized. Runs saved
 *  before then still carry these ids and must still read; they are never
 *  offered in a picker. */
const LEGACY_POLICY_LABELS: Record<string, string> = {
  defer_1yr: "Skip year 1, then convert (greedy)",
  fill_10: "Fill the 10% bracket (greedy)",
  fill_12: "Fill the 12% bracket (greedy)",
  fill_22: "Fill the 22% bracket (greedy)",
  fill_24: "Fill the 24% bracket (greedy)",
  fill_irmaa_tier: "Fill to next IRMAA tier (greedy)",
  level_25: "Convert ~5% of the IRA (greedy)",
  level_50: "Convert ~10% of the IRA (greedy)",
  level_100: "Convert ~20% of the IRA (greedy)",
  max_pre_rmd: "Spread IRA evenly before RMDs (greedy)",
};

const THRU_RE = /^fill_(\d+)_thru_(\d{4})$/;
const LEVEL_RE = /^level_(\d+)pct_(?:annual|thru_(\d{4}))$/;

/** The [id, label] pairs to offer in a strategy picker.
 *
 *  Which policies exist is a property of the INPUTS, not a fixed menu. A
 *  rule that never finds room is not generated, and the `_thru_<YYYY>` years
 *  depend on when each rule converts. Offering the full list let a user pick something the
 *  optimizer could not run, and the only feedback was an HTTP 400.
 *
 *  An empty `available` means "not known" (still loading, or the lookup
 *  failed) and shows everything — a best-effort call must not leave the user
 *  with no choices at all.
 */
export function strategyOptions(
  available: string[],
  startTraditional?: number | null,
): [string, string][] {
  const all = Object.entries(POLICY_LABELS) as [string, string][];
  if (available.length === 0) return all;
  const known = all.filter(([id]) => available.includes(id));
  // Bracket rules, then fixed amounts; each by rate or share as a number (an
  // id sort put "level_10pct" before "level_5pct"), every-year before years.
  const order = (id: string): [number, number, number] => {
    const m = THRU_RE.exec(id);
    if (m) return [0, Number(m[1]), Number(m[2])];
    const lv = LEVEL_RE.exec(id)!;
    return [1, Number(lv[1]), lv[2] ? Number(lv[2]) : 0];
  };
  const thru = available
    .filter((id) => THRU_RE.test(id) || LEVEL_RE.test(id))
    .sort((a, b) => {
      const [x, y] = [order(a), order(b)];
      return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
    })
    .map((id) => [id, policyLabel(id, startTraditional)] as [string, string]);
  return [...known, ...thru];
}

/** The yearly amount a level-dollar rule asks for: its share of the
 *  traditional balance at the start, computed once (backend
 *  policy_labels.level_amount). Null for other rules or without the balance. */
export function levelAmount(id: string, startTraditional?: number | null): number | null {
  const lv = LEVEL_RE.exec(id);
  if (!lv || startTraditional == null) return null;
  return (Number(lv[1]) / 100) * startTraditional;
}

/** A policy's name. With the starting traditional balance (a result's
 *  `starting_traditional_balance`) a level-dollar rule is named by its
 *  amount; runs saved before that field keep the percentage. */
export function policyLabel(id: string, startTraditional?: number | null): string {
  const m = THRU_RE.exec(id);
  if (m) return `Fill the ${m[1]}% bracket through ${m[2]}`;
  const lv = LEVEL_RE.exec(id);
  if (lv) {
    const amount = levelAmount(id, startTraditional);
    if (amount != null) {
      const usd = new Intl.NumberFormat("en-US", {
        style: "currency", currency: "USD", maximumFractionDigits: 0,
      }).format(amount);
      return `Convert up to ${usd} annually${lv[2] ? ` through ${lv[2]}` : ""}`;
    }
    const when = lv[2] ? `each year through ${lv[2]}` : "every year";
    return `Convert up to ${lv[1]}% of the starting IRA ${when}`;
  }
  return POLICY_LABELS[id] ?? LEGACY_POLICY_LABELS[id] ?? id;
}
