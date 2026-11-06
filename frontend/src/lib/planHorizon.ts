/** How long a plan is projected, from its "plan through" ages -- the rule
 *  backend api/assemble.py applies: the projection runs through the year the
 *  later of the two people reaches their age (inclusive), at least 10 years;
 *  with neither age set, 30 years. Ages are this calendar year's. */

interface Horizon {
  self_birth_date?: string | null;
  spouse_birth_date?: string | null;
  self_death_age?: number | null;
  spouse_death_age?: number | null;
}

/** Modelling default for a new plan, editable in the wizard. */
export const DEFAULT_PLAN_THROUGH_AGE = 95;

function birthYear(d: string | null | undefined): number | null {
  return d && d.length >= 4 ? Number(d.slice(0, 4)) : null;
}

/** The last projected calendar year, or null without a birth date. */
export function projectionEndYear(h: Horizon, year: number = new Date().getFullYear()): number | null {
  const bySelf = birthYear(h.self_birth_date);
  if (bySelf == null) return null;
  const bySpouse = birthYear(h.spouse_birth_date);
  const horizons: number[] = [];
  if (h.self_death_age != null) horizons.push(h.self_death_age - (year - bySelf) + 1);
  if (h.spouse_death_age != null && bySpouse != null)
    horizons.push(h.spouse_death_age - (year - bySpouse) + 1);
  const years = horizons.length ? Math.max(10, ...horizons) : 30;
  return year + years - 1;
}

/** Explicit ages that reproduce a saved plan's projection, for a plan saved
 *  with either age blank: each person is planned through the plan's existing
 *  end year, so copying the plan does not change what it projects. */
export function explicitPlanThroughAges(
  h: Horizon,
  year: number = new Date().getFullYear(),
): { self_death_age: number | null; spouse_death_age: number | null } {
  const end = projectionEndYear(h, year);
  const fill = (age: number | null | undefined, birth: string | null | undefined) => {
    if (age != null) return age;
    const by = birthYear(birth);
    return end == null || by == null ? null : end - by;
  };
  return {
    self_death_age: fill(h.self_death_age, h.self_birth_date),
    spouse_death_age: h.spouse_birth_date ? fill(h.spouse_death_age, h.spouse_birth_date) : null,
  };
}
