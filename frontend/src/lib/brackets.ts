/** Choices for the "Max ordinary-income bracket" cap, shared by the wizard
 *  and the What-if page so the two lists cannot drift apart.
 *
 *  Every statutory bracket that has a top. 10% is the ceiling that pairs with
 *  "Fill the 10% bracket"; 37% has no top, so "No limit" covers it. */
export const BRACKET_CAP_OPTIONS: { value: string; label: string }[] = [
  0.1, 0.12, 0.22, 0.24, 0.32, 0.35,
].map((rate) => ({ value: String(rate), label: `${Math.round(rate * 100)}% bracket` }));

/** The Select value for a stored cap. Constraints come back from the API as
 *  JSON strings ("0.12"), and the same cap can be spelled "0.1" or "0.10",
 *  so normalise through Number before matching an option. */
export function bracketCapSelectValue(cap: number | string | null | undefined): string {
  return cap == null || cap === "" ? "none" : String(Number(cap));
}
