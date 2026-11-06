/** Plain labels for stored setting values, shared by the wizard, the
 *  results inputs panel and the What-if page so each says the same thing. */

/** Medicare surcharge (IRMAA) setting. Four values are stored, but the
 *  optimizer has two behaviours (backend actions._TIER_POLICIES = strict,
 *  avoid), so the wizard offers two choices. Older plans keep their stored
 *  value; `irmaaChoice` maps it onto the choice with the same behaviour. */
export const IRMAA_CHOICES = [
  {
    value: "soft",
    label: "Allow conversions to cross Medicare surcharge thresholds",
    description: "The model includes the surcharge cost.",
  },
  {
    value: "strict",
    label: "Restrict conversions at Medicare surcharge thresholds",
    description: "A conversion that would cross the next threshold is dropped.",
  },
] as const;

export type IrmaaChoice = (typeof IRMAA_CHOICES)[number]["value"];

/** The choice a stored value behaves as: ignore = soft, avoid = strict. */
export function irmaaChoice(policy: string | null | undefined): IrmaaChoice {
  return policy === "strict" || policy === "avoid" ? "strict" : "soft";
}

/** Short form for summaries, by stored value. */
export const IRMAA_LABELS: Record<string, string> = {
  ignore: "May cross surcharge thresholds",
  soft: "May cross surcharge thresholds",
  strict: "Restricted at surcharge thresholds",
  avoid: "Restricted at surcharge thresholds",
};

export const FILING_LABELS: Record<string, string> = {
  joint: "Married filing jointly",
  single: "Single",
};

export const ACCOUNT_LABELS: Record<string, string> = {
  traditional: "Traditional IRA / 401(k)",
  roth: "Roth",
  taxable: "Taxable brokerage",
};

export const OWNER_LABELS: Record<string, string> = {
  self: "you",
  spouse: "spouse",
  joint: "joint",
};

/** "2026–2028", "from 2030", "through 2028", or "" (every year). */
export function yearSpan(start?: number | null, end?: number | null): string {
  if (start != null && end != null) return start === end ? `${start}` : `${start}–${end}`;
  if (start != null) return `from ${start}`;
  if (end != null) return `through ${end}`;
  return "";
}
