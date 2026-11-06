import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { HouseholdPayload, HouseholdDetail, AccountIn, IncomeIn } from "@/lib/types";
import { noCapitalGains } from "@/lib/capitalGains";
import { DEFAULT_CLAIM_MODES, type ClaimMode, type ClaimModes, type PersonKey } from "@/lib/claimSetup";
import { planPayload } from "@/lib/planPayload";
import { DEFAULT_PLAN_THROUGH_AGE, explicitPlanThroughAges } from "@/lib/planHorizon";

// ---------------------------------------------------------------------------
// Draft TTL — discard persisted drafts older than 24 hours
// ---------------------------------------------------------------------------

const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;

/** Household, Assumptions, Accounts, Income & SS, Spending and goals, Review and run. */
export const LAST_STEP = 5;

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const STARTER_ACCOUNT: AccountIn = {
  account_type: "taxable",
  owner: "self",
  balance: 0,
  basis: 0,
};

const STARTER_INCOME: IncomeIn = {
  category: "salary",
  owner: "self",
  amount: 0,
};

function defaultData(): HouseholdPayload {
  return {
    household: {
      filing_status: "joint",
      state: "CA",
      self_birth_date: "",
      spouse_birth_date: "",
      nickname: "",
      // A visible, editable planning default -- not a blank that silently
      // means "30 years" (see lib/planHorizon).
      self_death_age: DEFAULT_PLAN_THROUGH_AGE,
      spouse_death_age: DEFAULT_PLAN_THROUGH_AGE,
    },
    accounts: [{ ...STARTER_ACCOUNT }],
    income: [],
    settings: {
      required_spending: 90000,
      inflation: 0.03,
      nominal_return: 0.06,
      ss_pia_self: 0,
      // No age until the user gives one: with "Find the best eligible age"
      // it is optional (the comparison), with "Use an age I choose" it is
      // required. A default here would be an age nobody chose.
      ss_claim_age_self: null,
      ss_claim_age_spouse: null,
      // Unanswered until the user says Yes or No: an explicit question, not a
      // default that reads as "not receiving". Step 4 requires an answer from
      // anyone 62 or older; a plan saved before the question existed keeps
      // its NULL (see loadFrom) for the same reason.
      ss_receiving_self: null,
      ss_receiving_spouse: null,
      // Heir tax rate — stored explicitly so what the form displays is
      // exactly what gets saved (see ss_claim_age_spouse lesson above).
      // (The Estate/Balanced/Lifetime-taxes priority was retired: the
      // optimizer now maximizes the after-tax estate less unfunded spending.)
      heir_tax_rate: 0.25,
      // Same lesson: the toggle renders "fixed" via `?? "fixed"`, so the stored
      // value has to BE "fixed" or an untouched control saves NULL.
      spending_rule: "fixed",
    },
    constraints: {
      irmaa_policy: "soft",
      conversion_window: "anytime",
      preserve_taxable: false,
    },
    capital_gains: noCapitalGains(),
  };
}

// ---------------------------------------------------------------------------
// Deep merge defaults helper — ensures persisted data fills in with defaults
// Recursively merges stored values over defaults; missing keys inherit defaults.
// ---------------------------------------------------------------------------

function deepMergeDefaults(defaults: unknown, stored: unknown): unknown {
  // If stored is null/undefined or not an object, use defaults
  if (stored === null || stored === undefined || typeof stored !== "object") {
    return defaults;
  }

  // For arrays, return stored as-is (don't merge element-wise)
  if (Array.isArray(stored)) {
    return stored;
  }

  // For plain objects, merge key by key
  if (typeof defaults === "object" && defaults !== null && !Array.isArray(defaults)) {
    const defaultRecord = defaults as Record<string, unknown>;
    const storedRecord = stored as Record<string, unknown>;
    const result: Record<string, unknown> = { ...defaultRecord };

    for (const key in storedRecord) {
      if (Object.prototype.hasOwnProperty.call(storedRecord, key)) {
        // Recursively merge nested objects
        if (
          defaultRecord[key] !== null &&
          typeof defaultRecord[key] === "object" &&
          !Array.isArray(defaultRecord[key]) &&
          storedRecord[key] !== null &&
          typeof storedRecord[key] === "object" &&
          !Array.isArray(storedRecord[key])
        ) {
          result[key] = deepMergeDefaults(defaultRecord[key], storedRecord[key]);
        } else {
          // Use stored value (overrides defaults)
          result[key] = storedRecord[key];
        }
      }
    }
    return result;
  }

  return stored;
}


/** A saved plan as wizard data: stored values over the defaults, so a field
 *  added since it was saved gets its default.
 *
 *  DB round-trips return NULL for empty optional fields (e.g. a blank basis).
 *  Nulls must be STRIPPED before spreading: `null` would overwrite the default
 *  AND fail zod's .optional() (which accepts undefined, not null) — producing
 *  a silently blocked Next/Review button. */
function planFromDetail(detail: HouseholdDetail): HouseholdPayload {
  const stripNulls = <T extends object>(obj: T): Partial<T> =>
    Object.fromEntries(
      Object.entries(obj).filter(([, v]) => v !== null && v !== undefined)
    ) as Partial<T>;

  const base = defaultData();
  const loaded: HouseholdPayload = {
    household: {
      ...base.household,
      ...stripNulls(detail.household),
      // A plan saved with a blank age projected a fixed number of
      // years; spell that out rather than replace it with the default.
      ...explicitPlanThroughAges(detail.household),
    },
    accounts:
      detail.accounts.length > 0
        ? detail.accounts.map((a) => stripNulls(a) as typeof a)
        : base.accounts,
    income: detail.income.map((inc) => stripNulls(inc) as typeof inc),
    settings: {
      ...base.settings,
      ...stripNulls(detail.settings),
      // NULL is an answer here ("not stated"), not a missing field: keep
      // it so the wizard asks rather than silently saying "No".
      ss_receiving_self: detail.settings.ss_receiving_self ?? null,
      ss_receiving_spouse: detail.settings.ss_receiving_spouse ?? null,
      // Likewise "no age chosen" stays unchosen.
      ss_claim_age_self: detail.settings.ss_claim_age_self ?? null,
      ss_claim_age_spouse: detail.settings.ss_claim_age_spouse ?? null,
    },
    constraints: {
      ...base.constraints,
      ...stripNulls(detail.constraints),
    },
    // Gains entered for an earlier year are over: start this year blank.
    capital_gains:
      detail.capital_gains?.tax_year === base.capital_gains?.tax_year
        ? { ...detail.capital_gains! }
        : base.capital_gains,
  };
  return loaded;
}

// ---------------------------------------------------------------------------
// Immutable nested setter by dot-path
// Supports paths like:
//   "household.filing_status"
//   "accounts.0.balance"
//   "income.1.amount"
// ---------------------------------------------------------------------------

function setNested(obj: unknown, segments: string[], value: unknown): unknown {
  if (segments.length === 0) return value;
  const [head, ...tail] = segments;
  const idx = Number(head);
  if (!Number.isNaN(idx) && Array.isArray(obj)) {
    const arr = [...(obj as unknown[])];
    arr[idx] = setNested(arr[idx], tail, value);
    return arr;
  }
  const record = obj as Record<string, unknown>;
  return {
    ...record,
    [head]: setNested(record[head], tail, value),
  };
}

// ---------------------------------------------------------------------------
// Noop storage for environments without localStorage (SSR, node tests)
// ---------------------------------------------------------------------------

const noopStorage = {
  getItem: (_key: string): string | null => null,
  setItem: (_key: string, _value: string): void => {},
  removeItem: (_key: string): void => {},
};

function safeLocalStorage(): typeof noopStorage {
  if (typeof window !== "undefined" && typeof localStorage !== "undefined") {
    return localStorage;
  }
  return noopStorage;
}

// ---------------------------------------------------------------------------
// Store interface
// ---------------------------------------------------------------------------

export interface WizardStore {
  data: HouseholdPayload;
  step: number;
  /** Highest step index ever reached — controls which rail nodes are clickable. */
  visitedMax: number;
  /** Per person: search the claim age, or use the chosen one. Not part of
   *  the saved plan -- it decides which run the Review step starts. */
  claimModes: ClaimModes;
  setClaimModes: (m: ClaimModes) => void;
  /** Set one person's choice -- which also confirms it (see unconfirmedModes). */
  chooseMode: (who: PersonKey, m: ClaimMode) => void;
  /** The saved plan this draft belongs to, and the inputs it was saved with.
   *  Set once Review saves the plan, or when an unfinished plan is resumed:
   *  running then reuses that plan (updated in place if edited), never a copy. */
  resume: { householdId: string; savedKey: string } | null;
  setResume: (r: { householdId: string; savedKey: string } | null) => void;
  /** People whose claim-age choice was not recorded for a resumed plan: Review
   *  asks for them rather than guessing. */
  unconfirmedModes: PersonKey[];
  /** Open Review for a saved plan that never completed a run. *modes*: the
   *  choices recorded when it was saved, or null when unknown. */
  resumePlan: (detail: HouseholdDetail, modes: ClaimModes | null) => void;
  setField: (path: string, value: unknown) => void;
  addAccount: () => void;
  removeAccount: (i: number) => void;
  addIncome: () => void;
  removeIncome: (i: number) => void;
  next: () => void;
  back: () => void;
  /** Jump directly to a previously-visited step (rail navigation). */
  goToStep: (step: number) => void;
  reset: () => void;
  /** Clear persisted draft from localStorage and reset to defaults. */
  clearDraft: () => void;
  /** Load a previously saved household into the wizard (prefill from last plan). */
  loadFrom: (detail: HouseholdDetail) => void;
}

// ---------------------------------------------------------------------------
// Zustand store with persist middleware
// ---------------------------------------------------------------------------

export const useWizardStore = create<WizardStore>()(
  persist(
    (set, _get) => ({
      data: defaultData(),
      step: 0,
      visitedMax: 0,
      claimModes: { ...DEFAULT_CLAIM_MODES },
      setClaimModes: (m) => set({ claimModes: m }),
      chooseMode: (who, m) =>
        set((state) => ({
          claimModes: { ...state.claimModes, [who]: m },
          unconfirmedModes: state.unconfirmedModes.filter((p) => p !== who),
        })),
      resume: null,
      setResume: (r) => set({ resume: r }),
      unconfirmedModes: [],

      resumePlan: (detail, modes) => {
        const data = planFromDetail(detail);
        const claimModes: ClaimModes = modes ?? { ...DEFAULT_CLAIM_MODES };
        const unconfirmed: PersonKey[] = [];
        if (!modes) {
          // Deduce what can be deduced: a blank age was "find the best age"
          // (an age you choose is required). Anyone else with a choice to
          // make is asked on Review.
          const people: PersonKey[] = data.household.filing_status === "joint" ? ["self", "spouse"] : ["self"];
          for (const who of people) {
            const s = data.settings;
            const pia = who === "self" ? s.ss_pia_self : s.ss_pia_spouse;
            const claim = who === "self" ? s.ss_claim_age_self : s.ss_claim_age_spouse;
            const receiving = who === "self" ? s.ss_receiving_self : s.ss_receiving_spouse;
            const birth = who === "self" ? data.household.self_birth_date : data.household.spouse_birth_date;
            const age = birth ? new Date().getFullYear() - Number(birth.slice(0, 4)) : null;
            if (pia == null || receiving === true || (age != null && age >= 70)) continue;
            if (claim == null) claimModes[who] = "search";
            else unconfirmed.push(who);
          }
        }
        set({
          data,
          step: LAST_STEP,
          visitedMax: LAST_STEP,
          claimModes,
          unconfirmedModes: unconfirmed,
          resume: { householdId: detail.household_id, savedKey: JSON.stringify(planPayload(data)) },
        });
      },

      setField: (path, value) =>
        set((state) => ({
          data: setNested(state.data, path.split("."), value) as HouseholdPayload,
        })),

      addAccount: () =>
        set((state) => ({
          data: {
            ...state.data,
            accounts: [...state.data.accounts, { ...STARTER_ACCOUNT }],
          },
        })),

      removeAccount: (i) =>
        set((state) => ({
          data: {
            ...state.data,
            accounts: state.data.accounts.filter((_, idx) => idx !== i),
          },
        })),

      addIncome: () =>
        set((state) => ({
          data: {
            ...state.data,
            income: [...state.data.income, { ...STARTER_INCOME }],
          },
        })),

      removeIncome: (i) =>
        set((state) => ({
          data: {
            ...state.data,
            income: state.data.income.filter((_, idx) => idx !== i),
          },
        })),

      next: () =>
        set((state) => {
          const newStep = Math.min(state.step + 1, LAST_STEP);
          return {
            step: newStep,
            visitedMax: Math.max(state.visitedMax, newStep),
          };
        }),

      back: () =>
        set((state) => ({ step: Math.max(state.step - 1, 0) })),

      goToStep: (step) =>
        set((state) => {
          if (step >= 0 && step <= state.visitedMax) {
            return { step };
          }
          return {};
        }),

      reset: () =>
        set({ data: defaultData(), step: 0, visitedMax: 0, claimModes: { ...DEFAULT_CLAIM_MODES },
              resume: null, unconfirmedModes: [] }),

      clearDraft: () => {
        // Note: persist middleware will rewrite "wizard-draft" on next set,
        // so removeItem is not necessary. Kept for clarity but could be removed.
        if (typeof window !== "undefined") {
          try {
            localStorage.removeItem("wizard-draft");
          } catch {
            // ignore
          }
        }
        set({ data: defaultData(), step: 0, visitedMax: 0, claimModes: { ...DEFAULT_CLAIM_MODES },
              resume: null, unconfirmedModes: [] });
      },

      loadFrom: (detail: HouseholdDetail) => {
        const loaded = planFromDetail(detail);
        // Self-describing copy name: a forgotten rename must not create a
        // second plan with an identical nickname (60-char DB limit).
        loaded.household.nickname = detail.household.nickname
          ? `Copy of ${detail.household.nickname}`.slice(0, 60)
          : "";
        // A copy is a new plan: nothing to resume.
        set({ data: loaded, step: 0, visitedMax: 0, resume: null, unconfirmedModes: [] });
      },
    }),
    {
      name: "wizard-draft",
      version: 1,
      storage: createJSONStorage(() => safeLocalStorage()),
      partialize: (state) => ({
        data: state.data,
        step: state.step,
        visitedMax: state.visitedMax,
        claimModes: state.claimModes,
        resume: state.resume,
        unconfirmedModes: state.unconfirmedModes,
        savedAt: Date.now(),
      }),
      migrate: (persisted: unknown, fromVersion: number) => {
        // Handle migrations from older versions (if any).
        // For now, fromVersion 0 → 1 just returns as-is; merge() handles deep merging.
        if (fromVersion < 1) {
          // No structural changes needed; merge() will backfill defaults.
          return persisted;
        }
        return persisted;
      },
      merge: (persisted: unknown, current) => {
        if (persisted && typeof persisted === "object" && "data" in persisted) {
          const rec = persisted as Record<string, unknown>;
          // Discard drafts older than 24 hours
          if (typeof rec.savedAt === "number" && Date.now() - rec.savedAt > DRAFT_TTL_MS) {
            return current;
          }
          return {
            ...current,
            ...persisted,
            data: deepMergeDefaults(defaultData(), rec.data) as HouseholdPayload,
          };
        }
        return current;
      },
    }
  )
);
