import type { HouseholdPayload } from "@/lib/types";
import { capitalGainsPayload } from "@/lib/capitalGains";

/** The plan as it is saved: what the form holds, less what does not apply.
 *  A single filer's spouse fields (left over from switching filing status,
 *  or the form's blank "") would otherwise reach the API, which rejects a
 *  blank date and would read a leftover one as a spouse. */
export function planPayload(form: HouseholdPayload): HouseholdPayload {
  const data = {
    ...form,
    capital_gains: capitalGainsPayload(form.capital_gains),
    // The floor belongs to "cut back, then recover"; the form keeps a value
    // typed before switching back to "keep spending the same".
    settings: form.settings.spending_rule === "guardrails"
      ? form.settings
      : { ...form.settings, spending_floor: null },
  };
  if (data.household.filing_status === "joint") return data;
  const { spouse_birth_date: _b, spouse_death_age: _d, ...household } = data.household;
  const {
    ss_pia_spouse: _p,
    ss_claim_age_spouse: _c,
    ss_receiving_spouse: _r,
    ...settings
  } = data.settings;
  return {
    ...data,
    household,
    settings,
    accounts: data.accounts,
    income: data.income,
  } as HouseholdPayload;
}

/** The household fields that set the projection length, for this plan's
 *  filing status (lib/planHorizon). */
export function householdHorizon(data: HouseholdPayload) {
  const h = planPayload(data).household;
  return {
    self_birth_date: h.self_birth_date,
    spouse_birth_date: h.spouse_birth_date,
    self_death_age: h.self_death_age,
    spouse_death_age: h.spouse_death_age,
  };
}
