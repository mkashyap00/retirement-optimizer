import { narrativeFor } from "@/lib/zeroConversion";
import type { YearRow } from "@/lib/types";

const LEGACY =
  "No Roth conversion this year: either the conversion window is closed, or converting offered " +
  "no lifetime after-tax benefit (conversion strategies are always evaluated — see Alternative Policies).";

const row = (year: number, conversion: number, trad = 100000, narrative = LEGACY) =>
  ({ year, conversion, balance_traditional: trad, rationale: { narrative } }) as unknown as YearRow;

test("older runs' either/or sentence names the known reason", () => {
  const rows = [row(2026, 0), row(2027, 5000, 90000, "Converted"), row(2028, 0), row(2029, 0)];
  expect(narrativeFor(rows[0], rows, "fill_12_annual")).toBe(
    "No Roth conversion this year: the recommended strategy starts converting in 2027.");
  expect(narrativeFor(rows[2], rows, "fill_12_thru_2027")).toBe(
    "No Roth conversion this year: the recommended strategy converts only through 2027.");
  expect(narrativeFor(rows[0], rows, "none")).toBe(
    "No Roth conversion this year: the recommended strategy makes no Roth conversions.");
  // Any other narrative is left alone.
  expect(narrativeFor(rows[1], rows, "fill_12_annual")).toBe("Converted");
});

test("an older RMD sentence stands only when the bracket had no room left", () => {
  const OLD_RMD = "No conversion this year: RMD of $32,000 plus other income already fills the 22% bracket.";
  const rmdRow = (headroom: number) => ({
    year: 2031, conversion: 0, balance_traditional: 400000,
    rationale: {
      narrative: OLD_RMD,
      bracket: { bracket_rate: 0.22, bracket_top: 206700, headroom_used: 0, headroom_remaining: headroom },
      withdrawal: { order_used: ["rmd", "taxable"], reason: "", rmd_amount: 32000 },
    },
  }) as unknown as YearRow;
  const withRoom = rmdRow(10000);
  const rows = [row(2030, 5000, 500000, "Converted"), withRoom];
  expect(narrativeFor(withRoom, rows, "fill_22_annual")).toBe(
    "No Roth conversion this year: the recommended strategy's last conversion is in 2030. " +
    "This year's required minimum distribution is $32,000.");
  const full = rmdRow(0);
  expect(narrativeFor(full, [rows[0], full], "fill_22_annual")).toBe(OLD_RMD);
});
