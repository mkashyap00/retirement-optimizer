import { milestones } from "@/lib/milestones";
import type { YearRow } from "@/lib/types";

const rows = [2026, 2027, 2028, 2029, 2030, 2031].map((year, i) => ({
  year, age_self: 64 + i, age_spouse: 62 + i, rmd: year >= 2030 ? 1000 : 0,
})) as unknown as YearRow[];

test("salary end, claim years and the first RMD, merged by year", () => {
  expect(milestones(rows, {
    claimAges: { self: 67, spouse: 66 },
    income: [{ category: "salary", owner: "self", amount: 1, start_year: 2020, end_year: 2028 }],
  })).toEqual([
    { year: 2028, label: "Your salary ends" },
    { year: 2029, label: "You claim Social Security" },
    { year: 2030, label: "Spouse claims Social Security, RMDs begin" },
  ]);
});

test("someone already receiving has no start to mark; a past salary end is not shown", () => {
  expect(milestones(rows, {
    claimAges: { self: 67, spouse: 66 },
    receiving: { self: true },
    income: [{ category: "salary", owner: "spouse", amount: 1, end_year: 2020 }],
  }).map((m) => m.label)).toEqual(["Spouse claims Social Security, RMDs begin"]);
});

test("a claim in the first projection year is marked only for someone explicitly not receiving", () => {
  const claimNow = { self: 64, spouse: 62 };
  expect(milestones(rows, { claimAges: claimNow, receiving: { self: false, spouse: false } })
    .map((m) => m.label)).toEqual(["You claim Social Security, Spouse claims Social Security", "RMDs begin"]);
  expect(milestones(rows, { claimAges: claimNow, receiving: { self: true, spouse: true } })
    .map((m) => m.label)).toEqual(["RMDs begin"]);
  // Unknown (older runs): no first-year marker.
  expect(milestones(rows, { claimAges: claimNow }).map((m) => m.label)).toEqual(["RMDs begin"]);
});
