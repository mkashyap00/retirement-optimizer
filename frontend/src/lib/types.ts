// ---------------------------------------------------------------------------
// Primitive types
// ---------------------------------------------------------------------------

export type FilingStatus = "single" | "joint";
export type AccountType = "taxable" | "traditional" | "roth";
export type AccountOwner = "self" | "spouse" | "joint";
export type IncomeOwner = "self" | "spouse" | "joint";
export type IncomeCategory = "salary" | "pension" | "rental" | "interest" | "qualified_dividend" | "nonqualified_dividend";
export type IrmaaPolicy = "ignore" | "soft" | "strict" | "avoid";
export type ConversionWindow = "anytime" | "pre_medicare" | "pre_rmd" | "pre_ss";
export type BetrVerdict = "favorable" | "marginal" | "unfavorable";
export type SpendingRule = "fixed" | "guardrails";

// ---------------------------------------------------------------------------
// HouseholdPayload — nested shape matching backend HouseholdPayload model
// ---------------------------------------------------------------------------

export interface HouseholdIn {
  filing_status: FilingStatus;
  self_birth_date: string; // ISO date, e.g. "1960-03-15"
  spouse_birth_date?: string;
  state: string; // 2-letter uppercase, e.g. "CA"
  nickname?: string | null; // optional user-visible label, max 60 chars
  /** Age at which to end the projection for self (e.g. 95). Defaults to current_age + 30. */
  self_death_age?: number | null;
  /** Age at which to end the projection for spouse. Defaults to spouse_age + 30. */
  spouse_death_age?: number | null;
}

export interface AccountIn {
  account_type: AccountType;
  owner: AccountOwner;
  balance: number;
  basis?: number; // required for taxable accounts
  /** Year the Roth account was first opened (for 5-year rule). Only relevant for Roth accounts. */
  roth_opened_year?: number | null;
}

export interface IncomeIn {
  category: IncomeCategory;
  owner: IncomeOwner;
  amount: number;
  start_year?: number;
  end_year?: number;
}

export interface SettingsIn {
  required_spending: number;
  inflation: number;
  nominal_return: number;
  ss_pia_self: number;
  /** 62–70. null = no age chosen: only a claim-age search may run then,
   *  and it has no "your ages" comparison. */
  ss_claim_age_self: number | null;
  ss_pia_spouse?: number;
  ss_claim_age_spouse?: number | null;
  /** Already receiving benefits? Then the claim age is the age they claimed
   *  (≤ today's age); otherwise it is a plan (≥ today's age). null = not
   *  stated, on plans saved before the question existed. */
  ss_receiving_self?: boolean | null;
  ss_receiving_spouse?: boolean | null;
  /** Heirs' marginal rate on inherited traditional IRAs (0–1). Default 0.25. */
  heir_tax_rate?: number | null;
  /** Retired (October 2026): stored on older plans, ignored by the optimizer. */
  estate_weight?: number | null;
  /** "fixed" spends the target every year; "guardrails" flexes it with the
   *  withdrawal rate (Guyton-Klinger). Defaults to "fixed". */
  spending_rule?: SpendingRule | null;
  /** Essential spending in today's dollars. Guardrail cuts stop here, and it
   *  splits the consumption gap into discretionary and essential tiers.
   *  Null = no discretionary band; every dollar counts as essential. */
  spending_floor?: number | null;
  /** Projected annual Social Security COLA (fraction). Null/absent = follow
   *  the inflation assumption (floored at 0); 0 = benefits flat in dollars. */
  ss_cola?: number | null;
}

export interface ConstraintsIn {
  irmaa_policy: IrmaaPolicy;
  conversion_window: ConversionWindow;
  marginal_rate_limit?: number;
  max_conversion_per_year?: number;
  target_estate?: number;
  preserve_taxable: boolean;
}

/** Capital gains already realized in `tax_year` and the loss carried into
 *  it. Tax figures only: the sale proceeds are already in the balances.
 *  Applied when `tax_year` is the plan's first year. */
export interface CapitalGainsIn {
  tax_year: number;
  /** Net so far this year; negative is a net loss. */
  short_term: number;
  long_term: number;
  /** Loss carried in from last year's return (>= 0). */
  carryover_short_term: number;
  carryover_long_term: number;
}

/** Full planning request payload sent to POST /households. */
export interface HouseholdPayload {
  household: HouseholdIn;
  accounts: AccountIn[];
  income: IncomeIn[];
  settings: SettingsIn;
  constraints: ConstraintsIn;
  capital_gains?: CapitalGainsIn | null;
}

// ---------------------------------------------------------------------------
// Response shapes from GET /households and GET /households/{id}
// ---------------------------------------------------------------------------

export interface HouseholdSummary {
  household_id: string;
  filing_status: FilingStatus;
  state: string;
  created_at: string;
  nickname?: string | null;
}

export interface HouseholdDetail {
  household_id: string;
  household: HouseholdIn;
  accounts: AccountIn[];
  income: IncomeIn[];
  settings: SettingsIn;
  constraints: ConstraintsIn;
  capital_gains?: CapitalGainsIn | null;
}

// ---------------------------------------------------------------------------
// OptimizationResult — mirrors optimizer.py run_optimization() return dict
// ---------------------------------------------------------------------------

export interface MarketModel {
  scenarios: number;
  /** Assumed average annual return, e.g. 0.06. */
  mean_return: number;
  /** Standard deviation of each year's return, e.g. 0.12. */
  volatility: number;
  distribution: "normal";
  independent_years: boolean;
}

export interface BracketFacts {
  bracket_rate: number;
  bracket_top: number | null;
  headroom_used: number;
  headroom_remaining: number;
}

export interface ThresholdWarning {
  kind: string; // "irmaa_tier" | "niit" | "ltcg_0_to_15" | "salt_phase_down"
  threshold: number;
  distance: number; // negative = threshold already crossed
  consequence: string;
}

export interface ConversionRationale {
  action_id: string;
  amount: number;
  target_description: string;
  counterfactual_none_tax: number;
  marginal_cost_rate: number;
  betr: number;
  projected_future_marginal_rate: number;
  betr_verdict: BetrVerdict;
}

export interface WithdrawalRationale {
  order_used: string[];
  reason: string;
  rmd_amount: number;
}

export interface YearRationale {
  year: number;
  age_self: number;
  bracket: BracketFacts;
  conversion: ConversionRationale | null;
  withdrawal: WithdrawalRationale;
  warnings: ThresholdWarning[];
  narrative: string;
}

export interface YearRow {
  year: number;
  age_self: number;
  age_spouse?: number | null;
  conversion: number;
  withdrawal_taxable: number;
  withdrawal_traditional: number;
  withdrawal_roth: number;
  rmd: number;
  agi: number;
  magi: number;
  federal_tax: number;
  state_tax: number;
  irmaa: number;
  total_tax: number;
  effective_rate: number;
  marginal_rate: number;
  net_spendable: number;
  /** What the plan tried to fund: the target, or the reduced amount the
   *  spending rule allowed. */
  required_spending: number;
  /** The un-cut goal. Equals required_spending under the fixed rule; absent on
   *  runs stored before dynamic spending shipped. */
  target_spending?: number;
  /** Spending the guardrails chose to give up this year (0 under "fixed"). */
  discretionary_cut?: number;
  /** Spending this year could not fund after draining every account; 0 when
   *  fully funded. Absent on runs stored before partial shortfalls shipped. */
  shortfall?: number;
  balance_taxable: number;
  balance_traditional: number;
  balance_roth: number;
  rationale: YearRationale;
}

export interface TaxTables {
  federal_published_through: number;
  irmaa_published_through: number;
  state_published_through: number;
  /** States whose later years are projected; others keep their last table. */
  state_indexed: string[];
  indexation_rate: number;
  irmaa_premiums_projected: boolean;
}

/** What a policy's score is made of. basis "deterministic" = the policy's
 *  expected-return path, so these reconcile with deterministic_value, not with
 *  the Monte Carlo score. Absent on runs saved before October 2026. */
export interface ScoreComponents {
  basis: "deterministic";
  terminal_estate_pv: number;
  shortfall_pv: number;
  discretionary_shortfall_pv: number;
  shortfall_weight: number;
  discretionary_shortfall_weight: number;
  deterministic_value: number;
  /** Reported, not scored: the estate is already net of every tax paid. */
  lifetime_taxes_pv: number;
}

/** A joint claim-age search's breakdown: means over the Monte Carlo paths the
 *  score rests on, so it reconstructs `score` (to rounding). */
export interface MonteCarloScoreComponents {
  basis: "monte_carlo";
  monte_carlo_paths: number;
  estate_pv: number;
  shortfall_pv: number;
  discretionary_shortfall_pv: number;
  shortfall_weight: number;
  discretionary_shortfall_weight: number;
  score: number;
  lifetime_taxes_pv: number;
}

/** Identifies a candidate in a joint claim-age search: `policy@self-spouse`. */
export interface JointCandidateFields {
  key?: string;
  claim_age_self?: number | null;
  claim_age_spouse?: number | null;
  /** Joint runs: the expected-return breakdown, kept beside the MC one. */
  deterministic_score_components?: ScoreComponents;
}

export interface WinningPolicy extends JointCandidateFields {
  policy_id: string;
  lifetime_taxes_nominal: number;
  lifetime_taxes_pv: number;
  /** Rate lifetime_taxes_pv is discounted at. Absent on runs saved before it
   *  was reported; those all used the fixed 2% default. */
  discount_rate?: number;
  terminal_estate: number;
  success_probability: number;
  /** Scenarios this policy was actually scored on — the n of the success
   *  interval. monte_carlo_runs is the request. Absent on older runs. */
  monte_carlo_paths?: number;
  score: number;
  total_conversions: number;
  /** This year's conversion. Absent on runs saved before it was reported;
   *  yearly_plan[0].conversion carries the same figure for those. */
  year0_conversion?: number;
  projected_future_marginal_rate: number;
  /** Average years spending landed below target across the Monte Carlo
   *  scenarios. Shown beside success probability, because once spending can
   *  flex "the plan never failed" and "the plan delivered what you asked for"
   *  are different claims. Absent on pre-dynamic-spending runs. */
  mean_years_reduced?: number;
  score_components?: ScoreComponents | MonteCarloScoreComponents;
}

/** Winner vs. one alternative, compared on identical return sequences.
 *  Differences are winner − alternative, so positive favours the winner. */
export interface PairedComparison {
  /** "unresolved" means the simulation cannot tell which is better at this
   *  budget — NOT that they are equivalent, which is a separate verdict. */
  verdict: "winner" | "alternative" | "unresolved" | "equivalent";
  mean_difference: number;
  median_difference: number;
  std_error: number;
  ci_low: number;
  ci_high: number;
  winner_win_fraction: number;
  both_feasible: number;
  winner_only_feasible: number;
  alternative_only_feasible: number;
  both_infeasible: number;
  both_feasible_mean_difference: number;
}

export interface AlternativePolicy extends JointCandidateFields {
  policy_id: string;
  lifetime_taxes_delta: number; // positive = costs more than winner
  terminal_estate_delta: number; // positive = larger estate than winner
  success_probability_delta: number; // positive = higher success than winner
  /** Scenarios this strategy was scored on; fewer than the winner's when it
   *  was eliminated early. Absent on older runs. */
  monte_carlo_paths?: number;
  /** This strategy's OWN first-year conversion (absolute, not a delta), and
   *  its whole-horizon total. Absent on runs saved before they were reported. */
  year0_conversion?: number;
  total_conversions?: number;
  /** Calendar year of its first non-zero conversion; null = never converts.
   *  Absent on runs saved before it was reported. */
  first_conversion_year?: number | null;
  /** Absent on runs created before paired comparison shipped. */
  paired?: PairedComparison;
  /** Joint runs: its own full-sample Monte Carlo score. */
  score?: number;
  score_components?: ScoreComponents | MonteCarloScoreComponents;
}

// ---------------------------------------------------------------------------
// Joint claim-age search (result.search, mode "joint" | "joint_deterministic")
// ---------------------------------------------------------------------------

export interface ClaimExclusion {
  person: "self" | "spouse";
  age: number;
  reason: string;
}

/** One candidate as the search scored it. */
export interface JointCandidate {
  key: string;
  policy_id: string;
  claim_age_self: number | null;
  claim_age_spouse: number | null;
  eligible: boolean;
  conversion_stop_year: number | null;
  total_conversions: number;
  score: number;
  success_probability: number;
  monte_carlo_paths: number;
  fully_sampled: boolean;
  /** Means over its scenarios; absent on older runs. */
  score_components?: CandidateComponents | null;
}

/** What a candidate's average score is made of, in today's dollars. */
export interface CandidateComponents {
  estate_pv: number;
  shortfall_pv: number;
  discretionary_shortfall_pv: number;
}

export interface JointScenarioRow {
  key: string;
  claim_age_self: number | null;
  claim_age_spouse: number | null;
  eligible: boolean;
  entered: boolean;
  deterministic: { policy_id: string; value: number; policies: number };
  /** Best candidate on the common first `paths` scenarios. */
  stage1: { policy_id: string; score: number; paths: number };
  /** Best fully sampled candidate in this pair, when any reached the full sample. */
  final: { policy_id: string; score: number; paths: number } | null;
}

export interface SensitivityRow {
  variant: string;
  results: {
    key: string;
    score: number;
    success_probability: number;
    vs_winner: number;
  }[];
}

export interface JointSearch {
  mode: "joint";
  controls: Record<"self" | "spouse", { mode: "fixed" | "search"; age: number | null }>;
  exclusions: ClaimExclusion[];
  scenarios: JointScenarioRow[];
  stages: {
    stage1_runs: number;
    winner_stage1_score?: number;
    final_runs: number;
    candidates: number;
    finalists: JointCandidate[];
    per_scenario_breadth: number;
  };
  baselines: {
    /** Absent when a searched age had no comparison age: there are no
     *  "your ages" to compare with. */
    entered_no_conversion?: JointCandidate;
    entered_best_conversion?: JointCandidate;
    winner_ages_no_conversion: JointCandidate;
  };
  comparisons: Record<string, PairedComparison & { key: string }>;
  materiality: number;
  sensitivity: SensitivityRow[];
  assumptions: { ss_cola: number | null; seed: number; magi_proxy_note: string };
  schedules: Record<string, number[]>;
  timings_seconds: Record<string, number>;
}

export interface JointDeterministicSearch {
  mode: "joint_deterministic";
  exclusions: ClaimExclusion[];
  deterministic_matrix: {
    key: string;
    claim_age_self: number | null;
    claim_age_spouse: number | null;
    eligible: boolean;
    entered: boolean;
    policy_id: string;
    value: number;
    policies: number;
  }[];
}

/** POST /optimize/jobs body: per person, fixed (at age, or the stored one) or search. */
export interface ClaimSearchControls {
  self: { mode: "fixed" | "search"; age?: number | null };
  spouse: { mode: "fixed" | "search"; age?: number | null };
}

export interface OptimizeJob {
  id: string;
  household_id: string;
  status: "queued" | "running" | "done" | "failed";
  phase: "deterministic" | "monte_carlo" | "sensitivity" | null;
  progress: { done: number; total: number };
  run_id: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface OptimizationResult {
  status: string;
  /** Objective the run was scored with. Absent on runs saved before October
   *  2026, which used the retired taxes-vs-estate priority. */
  objective?: string;
  /** Where the tax tables came from. Absent on runs saved before tables were
   *  projected past their last published year (those froze them). */
  tax_tables?: TaxTables;
  computation_time_seconds: number;
  paths_evaluated: number;
  monte_carlo_runs: number;
  /** How the market scenarios were drawn. Absent on runs saved before
   *  October 2026 (same model; the page then omits the technical sentence). */
  market_model?: MarketModel;
  /** Traditional balance at the start; level-dollar rules convert a share of
   *  it. Absent on runs saved before October 2026. */
  starting_traditional_balance?: number;
  winning_policy: WinningPolicy;
  yearly_plan: YearRow[];
  alternative_policies: AlternativePolicy[];
  warnings: string[];
  /** Set when the run was forced to a specific policy instead of optimized. */
  forced_policy?: string | null;
  /** What the optimizer itself chose on these inputs: the winner on a normal
   *  run, the plan a forced run is shown instead of. Absent on older runs. */
  optimizer_pick?: string;
  /** Fixed-age runs: `none` at the same ages on the same paths -- what
   *  converting adds. Absent on runs saved before it was reported. */
  baseline_no_conversion?: {
    policy_id: string;
    score: number;
    success_probability: number;
    monte_carlo_paths: number;
    /** Recommendation − baseline. */
    score_difference: number;
    is_recommendation: boolean;
    paired: PairedComparison | null;
    /** Both sides' means on the same scenarios; absent on older runs. */
    score_components?: CandidateComponents | null;
    recommendation_score_components?: CandidateComponents | null;
  } | null;
  /** Gap treated as immaterial ("Practically equivalent"). */
  materiality?: number;
  /** Ages a "Run this policy" run was pinned to (null = the stored ones). */
  pinned_claim_ages?: { self: number | null; spouse: number | null } | null;
  /** The claim ages this run used. */
  claim_ages?: { self: number | null; spouse: number | null };
  /** Present on a joint claim-age search. */
  search?: JointSearch | JointDeterministicSearch;
  joint_winner?: JointCandidate;
}

// ---------------------------------------------------------------------------
// Run shapes from GET /runs/{id} and GET /households/{id}/runs
// ---------------------------------------------------------------------------

export interface RunDetail {
  run_id: string;
  household_id: string;
  created_at: string;
  result: OptimizationResult;
  /** Snapshot of the inputs that produced this run (null for old runs). */
  inputs?: HouseholdDetail | null;
}

export interface RunSummary {
  run_id: string;
  created_at: string;
  duration_ms: number;
  /** The pinned policy for a "Run this policy" run; null for an optimized
   *  run. Absent from servers that predate it. */
  forced_policy?: string | null;
  /** True for a joint claim-age search. Absent from older servers. */
  claim_search?: boolean;
}

// ---------------------------------------------------------------------------
// Scenario comparison types
// ---------------------------------------------------------------------------

export interface CompareConstraints {
  irmaa_policy?: IrmaaPolicy;
  conversion_window?: ConversionWindow;
  marginal_rate_limit?: number;
  max_conversion_per_year?: number;
  target_estate?: number;
  preserve_taxable?: boolean;
}

/** Per-scenario what-if overrides; omitted fields use the stored household values. */
export interface CompareOverrides {
  required_spending?: number;
  ss_claim_age_self?: number;
  ss_claim_age_spouse?: number;
  /** Retired (October 2026): accepted by the API and ignored. */
  estate_weight?: number;
  /** Force this conversion policy instead of letting the optimizer choose. */
  policy_id?: string;
  /** Model the first death at this age, switching the survivor to single
   *  filing with one Social Security benefit. Offered only as a what-if:
   *  modelling a death needs a year, and that guess belongs in a comparison
   *  the user asked for, not inside their plan of record. */
  first_death_age?: number;
  /** Whether the spouse (default) or self dies first. */
  first_death_is_spouse?: boolean;
  /** "fixed" or "guardrails" — see SettingsIn.spending_rule. */
  spending_rule?: SpendingRule;
  /** Essential spending floor in today's dollars. Omitted = use the stored
   *  floor; null = clear it (no floor). */
  spending_floor?: number | null;
}

export interface CompareDifference {
  /** a − b; positive = Scenario A has higher lifetime taxes */
  lifetime_taxes_delta: number;
  /** a − b; positive = Scenario A has larger terminal estate */
  terminal_estate_delta: number;
  /** a − b; positive = Scenario A has higher success probability */
  success_probability_delta: number;
  /** First calendar year where cumulative (taxes_a − taxes_b) changes sign; null if never */
  breakeven_year: number | null;
}

export interface CompareResult {
  result_a: OptimizationResult;
  result_b: OptimizationResult;
  difference: CompareDifference;
}

// ---------------------------------------------------------------------------
// Health + LLM narrative types
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  llm: boolean;
}

export interface NarrativeResponse {
  narrative: string;
}

// ---------------------------------------------------------------------------
// Portfolio tax-lot types
// ---------------------------------------------------------------------------

export interface PortfolioUploadResponse {
  lots: number;
  warnings: string[];
}

export interface SoldLotEntry {
  ticker: string;
  account_type: string;
  lot_date: string | null;
  holding_period: "long_term" | "short_term" | "unknown";
  shares_sold: number;
  proceeds: number;
  realized_gain: number;
}

export interface SalePlanResponse {
  target_cash: number;
  cash_raised: number;
  realized_lt_gain: number;
  realized_st_gain: number;
  sold: SoldLotEntry[];
  warnings: string[];
}

export interface PortfolioPosition {
  ticker: string;
  account_type: string;
  shares: number;
  price: number;
  market_value: number;
  cost_basis: number;
  holding_period: "long_term" | "short_term" | "unknown";
}

export interface PortfolioSummary {
  positions: PortfolioPosition[];
  uploaded_at: string | null;
  warnings: string[];
}
