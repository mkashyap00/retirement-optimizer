/**
 * Zod schemas for each wizard step.
 * Each schema validates the *subset* of HouseholdPayload relevant to that step.
 * Used for per-step Next-gating and inline field error display.
 */

import { z } from "zod";
import type { HouseholdPayload } from "@/lib/types";
import { DEFAULT_CLAIM_MODES, type ClaimModes } from "@/lib/claimSetup";

// ---------------------------------------------------------------------------
// Step 1 — Household Profile
// ---------------------------------------------------------------------------

const VALID_BIRTH = z
  .string()
  .min(1, "Birth date is required")
  .refine((d) => {
    const year = parseInt(d.split("-")[0] ?? "", 10);
    return year >= 1920 && year <= 2010;
  }, "Birth date must be between 1920 and 2010");

const PLAN_THROUGH = z
  .number({ required_error: "Enter the age to plan through", invalid_type_error: "Enter the age to plan through" })
  .int("Enter a whole number")
  .min(40, "Plan through at least age 40")
  .max(120, "Plan through age 120 at most");

export const step1Schema = z
  .object({
    filing_status: z.enum(["single", "joint"]),
    self_birth_date: VALID_BIRTH,
    spouse_birth_date: z.string().optional(),
    state: z.string().min(2, "State is required"),
    nickname: z.string().optional(),
    self_death_age: PLAN_THROUGH,
    spouse_death_age: PLAN_THROUGH.nullish(),
  })
  .refine(
    (h) => {
      if (h.filing_status === "joint") {
        return !!h.spouse_birth_date && h.spouse_birth_date.length >= 10;
      }
      return true;
    },
    {
      message: "Spouse birth date is required for joint filers",
      path: ["spouse_birth_date"],
    }
  )
  .refine((h) => h.filing_status !== "joint" || h.spouse_death_age != null, {
    message: "Enter the age to plan through",
    path: ["spouse_death_age"],
  })
  .refine((h) => passedAge(h.self_birth_date, h.self_death_age), {
    message: "Choose an age you have not reached yet",
    path: ["self_death_age"],
  })
  .refine(
    (h) => h.filing_status !== "joint" || passedAge(h.spouse_birth_date, h.spouse_death_age),
    { message: "Choose an age your spouse has not reached yet", path: ["spouse_death_age"] },
  );

/** False when the plan-through age is already behind this year's age. */
function passedAge(birth: string | undefined, through: number | null | undefined): boolean {
  if (!birth || birth.length < 4 || through == null) return true;
  return through >= new Date().getFullYear() - Number(birth.slice(0, 4));
}

// ---------------------------------------------------------------------------
// Step 2 — Assumptions
// ---------------------------------------------------------------------------

export const step2Schema = z.object({
  inflation: z.number().min(0, "Must be ≥ 0").max(1, "Must be ≤ 100%"),
  nominal_return: z.number().min(0, "Must be ≥ 0").max(1, "Must be ≤ 100%"),
  irmaa_policy: z.enum(["ignore", "soft", "strict", "avoid"]),
  conversion_window: z.enum(["anytime", "pre_medicare", "pre_rmd", "pre_ss"]),
});

// ---------------------------------------------------------------------------
// Step 3 — Accounts
// ---------------------------------------------------------------------------

const accountRowSchema = z
  .object({
    account_type: z.enum(["taxable", "traditional", "roth"]),
    owner: z.enum(["self", "spouse", "joint"]),
    balance: z.number().min(0, "Balance must be ≥ 0"),
    // .nullish(): DB restores use null for "no basis"; the taxable refine
    // below still rejects null/undefined basis on taxable accounts.
    basis: z.number().min(0).nullish(),
    roth_opened_year: z.number().min(1998, "Roth IRAs began in 1998").max(2100).nullable().optional(),
  })
  .refine(
    (a) => {
      if (a.account_type === "taxable") return a.basis != null;
      return true;
    },
    { message: "Taxable account requires a cost basis", path: ["basis"] }
  )
  // A taxable account may sit at a loss (basis above value). A traditional
  // after-tax basis cannot exceed what is in the account.
  .refine(
    (a) => {
      if (a.account_type === "traditional" && a.basis != null && a.basis > a.balance)
        return false;
      return true;
    },
    { message: "After-tax basis cannot exceed balance", path: ["basis"] }
  )
  // The 5-year rule counts from the year the first Roth was opened.
  .refine(
    (a) => a.account_type !== "roth" || a.balance <= 0 || a.roth_opened_year != null,
    {
      message: "Enter the year this Roth was first opened — the 5-year rule depends on it",
      path: ["roth_opened_year"],
    }
  )
  .refine(
    (a) => a.roth_opened_year == null || a.roth_opened_year <= new Date().getFullYear(),
    { message: "The year opened cannot be in the future", path: ["roth_opened_year"] }
  );

export const step3Schema = z.object({
  accounts: z.array(accountRowSchema),
});

// ---------------------------------------------------------------------------
// Step 4 — Income & Social Security
// ---------------------------------------------------------------------------

// Optional numerics use .nullish(): data restored from the DB or an old
// localStorage draft may hold null where the form would produce undefined.
export const step4Schema = z.object({
  ss_pia_self: z.number().min(0, "PIA must be ≥ 0"),
  ss_claim_age_self: z.number().min(62).max(70).nullish(),
  ss_pia_spouse: z.number().min(0).nullish(),
  ss_claim_age_spouse: z.number().min(62).max(70).nullish(),
});

// ---------------------------------------------------------------------------
// Step 5 — Spending and goals
// ---------------------------------------------------------------------------

export const step5Schema = z
  .object({
    required_spending: z.number().gt(0, "Enter how much you would like to spend each year"),
    spending_floor: z.number().min(0).nullish(),
  })
  .refine((s) => s.spending_floor == null || s.spending_floor <= s.required_spending, {
    message: "The minimum cannot be more than your annual spending",
    path: ["spending_floor"],
  });

// ---------------------------------------------------------------------------
// Validate the data slice relevant to the current step
// Returns { success, errors } where errors is a flat map of fieldPath → message
// ---------------------------------------------------------------------------

export type FieldErrors = Record<string, string>;

/** Mirrors the API's check (claiming.receiving_error): an actual claim cannot
 *  be later than today's age, nor a planned one earlier. Ages are this
 *  calendar year's, as the optimizer computes them. */
export function claimAgeConflict(
  birthDate: string | undefined | null,
  claimAge: number | undefined | null,
  receiving: boolean | undefined | null,
  year: number = new Date().getFullYear(),
): string | null {
  if (!birthDate || claimAge == null || receiving == null) return null;
  const age = year - Number(birthDate.slice(0, 4));
  if (receiving && claimAge > age)
    return `Already receiving: enter the age benefits started (${age} or earlier)`;
  const earliest = Math.min(age, 70);
  if (!receiving && claimAge < earliest)
    return `Age ${claimAge} has passed: choose ${earliest} or later, or answer "Yes" to already receiving`;
  return null;
}

export function validateStep(
  step: number,
  data: HouseholdPayload,
  /** Per person: the optimizer finds the claim age, or the user chooses it. */
  modes: ClaimModes = DEFAULT_CLAIM_MODES,
): { success: boolean; errors: FieldErrors } {
  let result:
    | z.SafeParseReturnType<unknown, unknown>
    | null = null;

  switch (step) {
    case 0:
      result = step1Schema.safeParse(data.household);
      break;
    case 1:
      result = step2Schema.safeParse({
        inflation: data.settings.inflation,
        nominal_return: data.settings.nominal_return,
        irmaa_policy: data.constraints.irmaa_policy,
        conversion_window: data.constraints.conversion_window,
      });
      break;
    case 2: {
      result = step3Schema.safeParse({ accounts: data.accounts });
      // Needs the household, so it is checked here rather than in the row
      // schema. A row left on "Spouse" after switching to single has no
      // owner the plan can age; the API rejects it.
      if (!data.household.spouse_birth_date) {
        const errors: FieldErrors = {};
        if (!result.success) {
          for (const issue of result.error.issues) {
            const key = issue.path.join(".");
            if (!errors[key]) errors[key] = issue.message;
          }
        }
        data.accounts.forEach((a, i) => {
          if (a.owner === "spouse")
            errors[`accounts.${i}.owner`] = "No spouse in this plan — choose Self";
        });
        if (Object.keys(errors).length > 0) return { success: false, errors };
        return { success: true, errors: {} };
      }
      break;
    }
    case 3: {
      result = step4Schema.safeParse({
        ss_pia_self: data.settings.ss_pia_self,
        ss_claim_age_self: data.settings.ss_claim_age_self,
        ss_pia_spouse: data.settings.ss_pia_spouse,
        ss_claim_age_spouse: data.settings.ss_claim_age_spouse,
      });
      const errors: FieldErrors = {};
      if (!result.success) {
        for (const issue of result.error.issues) {
          const key = issue.path.join(".");
          if (!errors[key]) errors[key] = issue.message;
        }
      }
      type Person = ["self" | "spouse", string | undefined | null, number | undefined | null,
        boolean | undefined | null, number | undefined | null];
      const people: Person[] = [
        ["self", data.household.self_birth_date, data.settings.ss_claim_age_self,
          data.settings.ss_receiving_self, data.settings.ss_pia_self],
      ];
      if (data.household.filing_status === "joint" && data.household.spouse_birth_date)
        people.push(["spouse", data.household.spouse_birth_date, data.settings.ss_claim_age_spouse,
          data.settings.ss_receiving_spouse, data.settings.ss_pia_spouse]);
      for (const [who, birth, claim, receiving, pia] of people) {
        const key = `ss_claim_age_${who}`;
        const msg = claimAgeConflict(birth, claim, receiving);
        if (msg && !errors[key]) errors[key] = msg;
        // From 62 the answer decides whether the age is a past claim or a
        // choice, so it is asked explicitly rather than assumed to be "No".
        const age = birth ? new Date().getFullYear() - Number(birth.slice(0, 4)) : null;
        if (age != null && age >= 62 && receiving == null) {
          errors[`ss_receiving_${who}`] =
            `Answer whether ${who === "self" ? "you are" : "your spouse is"} already receiving benefits`;
          continue;
        }
        // An age is needed for a claim already made and for "Use an age I
        // choose"; with "Find the best eligible age" it is an optional
        // comparison. No benefit entered: no age at all.
        if (pia == null || claim != null || errors[key]) continue;
        if (receiving === true) errors[key] = "Enter the age benefits started";
        else if (modes[who] === "fixed") errors[key] = "Choose a claim age, or let the optimizer find the best one";
      }
      if (Object.keys(errors).length > 0) return { success: false, errors };
      return { success: true, errors: {} };
    }
    case 4:
      result = step5Schema.safeParse({
        required_spending: data.settings.required_spending,
        // The minimum applies only when spending can be cut.
        spending_floor:
          data.settings.spending_rule === "guardrails" ? data.settings.spending_floor : null,
      });
      break;
    default:
      return { success: true, errors: {} };
  }

  if (!result || result.success) return { success: true, errors: {} };

  const errors: FieldErrors = {};
  for (const issue of result.error.issues) {
    const key = issue.path.join(".");
    if (!errors[key]) errors[key] = issue.message;
  }
  return { success: false, errors };
}
