/** What differs between two What-if scenarios (or a scenario and the saved
 *  plan), field by field, in words -- for the change highlights and the
 *  one-line summary of what a comparison will test. */

import type { CompareConstraints, CompareOverrides } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { IRMAA_LABELS, irmaaChoice } from "@/lib/labels";
import { policyLabel } from "@/lib/policyLabels";

export interface Scenario {
  constraints: CompareConstraints;
  overrides: CompareOverrides;
}

export type FieldKey =
  | "required_spending" | "ss_claim_age_self" | "ss_claim_age_spouse" | "spending_rule"
  | "spending_floor" | "first_death" | "policy_id" | "irmaa_policy" | "conversion_window"
  | "marginal_rate_limit" | "max_conversion_per_year";

const WINDOW: Record<string, string> = {
  anytime: "Anytime", pre_medicare: "Pre-Medicare", pre_rmd: "Pre-RMD", pre_ss: "Pre-Social Security",
};

const money = (v: unknown) => (v == null || v === "" ? "none" : formatCurrency(Number(v)));

/** Each field: how to read it from a scenario, and how to say its value. */
const FIELDS: {
  key: FieldKey; label: string; get: (s: Scenario) => unknown;
  /** *start*: the starting traditional balance, naming level-dollar rules by amount. */
  say: (v: unknown, start?: number | null) => string;
}[] = [
  { key: "required_spending", label: "Annual spending", get: (s) => s.overrides.required_spending, say: money },
  { key: "ss_claim_age_self", label: "Your claim age", get: (s) => s.overrides.ss_claim_age_self, say: String },
  { key: "ss_claim_age_spouse", label: "Spouse claim age", get: (s) => s.overrides.ss_claim_age_spouse, say: String },
  {
    key: "spending_rule", label: "If markets go badly",
    get: (s) => s.overrides.spending_rule ?? "fixed",
    say: (v) => (v === "guardrails" ? "cut back, then recover" : "keep spending the same"),
  },
  {
    // Only "cut back, then recover" has a floor; a value left from trying it is not a change.
    key: "spending_floor", label: "Essential floor",
    get: (s) => (s.overrides.spending_rule === "guardrails" ? s.overrides.spending_floor : null),
    say: money,
  },
  {
    key: "first_death", label: "First death",
    get: (s) => s.overrides.first_death_age == null
      ? null
      : `${s.overrides.first_death_is_spouse === false ? "you" : "spouse"} at ${s.overrides.first_death_age}`,
    say: (v) => (v == null ? "both alive" : String(v)),
  },
  {
    key: "policy_id", label: "Strategy", get: (s) => s.overrides.policy_id,
    say: (v, start) => (v == null ? "optimizer chooses" : policyLabel(String(v), start)),
  },
  {
    // By behaviour: a stored "ignore" and a chosen "soft" are the same setting.
    key: "irmaa_policy", label: "Medicare surcharge", get: (s) => irmaaChoice(s.constraints.irmaa_policy),
    say: (v) => IRMAA_LABELS[String(v)] ?? String(v),
  },
  {
    key: "conversion_window", label: "Conversion window", get: (s) => s.constraints.conversion_window ?? "anytime",
    say: (v) => WINDOW[String(v)] ?? String(v),
  },
  {
    key: "marginal_rate_limit", label: "Max bracket", get: (s) => s.constraints.marginal_rate_limit,
    say: (v) => (v == null ? "no limit" : `${Math.round(Number(v) * 100)}%`),
  },
  {
    key: "max_conversion_per_year", label: "Max conversion / year",
    get: (s) => s.constraints.max_conversion_per_year,
    say: (v) => (v == null ? "no limit" : formatCurrency(Number(v))),
  },
];

/** Stored values arrive as strings or numbers, and blank as null or undefined. */
function same(a: unknown, b: unknown): boolean {
  const norm = (v: unknown) => (v == null || v === "" ? null : typeof v === "number" || !isNaN(Number(v)) ? Number(v) : v);
  return norm(a) === norm(b);
}

export interface Change {
  key: FieldKey;
  label: string;
  from: string;
  to: string;
}

export function changes(from: Scenario, to: Scenario, start?: number | null): Change[] {
  return FIELDS.filter((f) => !same(f.get(from), f.get(to))).map((f) => ({
    key: f.key, label: f.label, from: f.say(f.get(from), start), to: f.say(f.get(to), start),
  }));
}

/** "Annual spending $90,000 → $80,000 · Your claim age 67 → 70" */
export function changeSummary(list: Change[]): string {
  return list.map((c) => `${c.label} ${c.from} → ${c.to}`).join(" · ");
}
