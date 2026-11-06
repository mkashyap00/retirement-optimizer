import { formatCurrency } from "@/lib/utils";

export type DeltaKind = "taxes" | "estate" | "success";

/**
 * One What-if difference (A − B, as the compare endpoint reports it) as a
 * sentence naming the scenario that comes out ahead.
 *
 * The cards used to show the signed number with a sign rule beneath it
 * ("Negative = Scenario A pays less tax"), and a +$125,643 was read as "A pays
 * less" — the opposite of what it meant. A difference too small to display
 * (under a dollar, or under 0.05 pts) reads "Same in both" rather than
 * naming a winner by a rounding error.
 */
export function describeDelta(
  aMinusB: number,
  kind: DeltaKind,
  names: { a: string; b: string } = { a: "Scenario A", b: "Scenario B" },
): string {
  if (kind === "success") {
    const pts = (Math.abs(aMinusB) * 100).toFixed(1);
    if (pts === "0.0") return "Same in both";
    const ahead = aMinusB > 0 ? names.a : names.b;
    return `${ahead}: ${pts} pts more likely to succeed`;
  }

  const amount = formatCurrency(Math.abs(aMinusB));
  if (amount === "$0") return "Same in both";
  if (kind === "taxes") {
    // Lower tax is better, so the scenario ahead is the one with less.
    const ahead = aMinusB < 0 ? names.a : names.b;
    return `${ahead}: ${amount} less tax`;
  }
  const ahead = aMinusB > 0 ? names.a : names.b;
  return `${ahead}: ${amount} larger estate`;
}
