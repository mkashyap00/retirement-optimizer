# Optimizer internals

How a recommendation is actually produced: what candidates exist, which ones
survive to be scored, how they are scored, and where the numbers can be
verified. This is the engineering companion to the [User Guide](USER_GUIDE.md), which
explains the results for a reader who does not want to open the code, and to
[How a recommendation is chosen](HOW_A_RECOMMENDATION_IS_CHOSEN.md), which walks
four example households through the search with reproducible numbers.

Every figure below was measured on the standard test household
(`backend/tests/integration/test_optimizer_pipeline.py`) unless stated
otherwise: 62/62 married filing jointly in California, $400k taxable with
$300k basis, $2.5M traditional, $50k Roth, $30k pension, $90k spending, 30-year
horizon, default settings.

---

## The pipeline

```
household inputs
      │
      ▼
generate_conversions()      actions.py      per-year candidate amounts
      │
      ▼
search()                    search.py       rules + their duration variants → POLICIES
      │                                     (95 on the standard household)
      ▼
sort by path_value          evaluate.py     deterministic ranking, single 6% path
      │
      ▼
score_policies_adaptive()   montecarlo.py   stage 1: every policy on runs//3 paths
      │                                     stage 2: top 3 + `none` extended to full budget
      ▼
compare_paired()            montecarlo.py   winner vs each runner-up, path by path
      │
      ▼
winning_policy + alternative_policies
```

Two rankings are involved and **they use different criteria**. `path_value`
ranks on a single deterministic path; the decision uses the mean Monte Carlo
objective. They can disagree, which is why Monte Carlo now scores every policy
— see [§4](#4-monte-carlo-scores-every-policy).

---

## 1. Candidate generation — `actions.py`

`generate_conversions(state, ...)` returns `(action_id, amount)` pairs for a
single year. `("none", 0)` is always first.

| candidate | amount |
|---|---|
| `fill_10` / `fill_12` / `fill_22` / `fill_24` / `fill_32` | the conversion that lands **taxable ordinary income** on that bracket's top |
| `level_5pct` / `level_10pct` / `level_20pct` | a caller-sized fixed amount (`requested=`): 5, 10 or 20% of the **starting** traditional balance, sized once in `search.py` |

Three more ids are still sized inside `generate_conversions` — `fill_irmaa_tier`
(MAGI just under the next IRMAA tier), `level_25/50/100` (¼, ½, 1× of
traditional ÷ `_LEVEL_DRAW_YEARS` = 5, the retired greedy window) and
`max_pre_rmd` (traditional ÷ years to the RMD age) — but the production search
is the only caller and always passes `only=rule_id`, so **none of them ever
becomes a policy**. They survive for the unit tests and as the origin of the
5/10/20% shares. For a reader-level account of the menu that results, see
[How a recommendation is chosen](HOW_A_RECOMMENDATION_IS_CHOSEN.md).

### Bracket sizing is not `bracket.upper − taxable_income`

A bracket's upper edge bounds **ordinary** income. `taxable_income` also
contains qualified dividends and long-term gains, which stack *above* ordinary
income on their own rate schedule, and it floors at zero, discarding any
deduction the baseline income did not use. The room is therefore

```
room = bracket.upper + deduction − baseline_ordinary
```

That closed form is exact only when the baseline holds every dollar of the
year's ordinary income and a converted dollar moves taxable ordinary income by
exactly one dollar. Three things break that:

- **Social Security** — a conversion raises provisional income, so more of the
  benefit becomes taxable, and that is itself ordinary income.
- **The senior bonus deduction** — it phases out with AGI, so a conversion can
  shrink the deduction the room was measured against. The $6,000 is phased out
  per person (Schedule 1-A lines 35–36), on top of the permanent age-65
  addition to the standard deduction ($1,650 per spouse, $2,050 single, 2026),
  which does not phase out but is lost when itemizing.
- **Spending drawn from the traditional IRA** — once the taxable account is
  empty, the year's spending (grossed up for its own tax and the conversion's)
  is an IRA withdrawal, which is ordinary income. It is only known once the
  year is solved, so the baseline never contains it.

The third went unhandled until October 2026: on the standard household
"Fill the 12% bracket every year" converted $103,000 a year from 2030 and landed
in the **24%** bracket, and a 12% cap let it through. So the closed form is now
only an upper bound. `_bracket_fill_amount()` simulates the year at that amount;
if taxable ordinary income lands at or below the bracket top the closed form
stands (one simulation), otherwise it bisects on the simulated year until it
does. `fill_irmaa_tier` uses the same technique against MAGI.

### Filters, applied in order

`amount ≤ 0 or < min_conversion` ($1,000) → drop · exceeds balance or
`max_conversion_per_year` → clamp, re-check minimum · would leave the year
shorter of spending money than converting nothing → cut back to the most the
year can spare (`_affordable_conversion`), re-check minimum · `conversion_window`
blocks → drop all non-none · `irmaa_policy` "strict" or "avoid" and the year
as simulated crosses the next tier → drop · `marginal_rate_limit` exceeded → drop · duplicate amount → keep
first. The annual-rule builder (`_build_rule_schedule`) asks for the list
without that last step (`dedupe=False`): under a cap, `fill_10` and `fill_22`
can size to the same amount, and a deduplicated list has no `fill_22` entry
for it to find — before October 2026 that rule then converted nothing.

The affordability cut exists because spending is funded from the Roth balance
as it stood at the start of the year: a conversion that takes IRA dollars the
year's spending needs used to leave the year short while the converted money
sat in the Roth. Found by the random-household invariants in
`tests/property/test_household_invariants.py` (October 2026).

`simulate_path` re-applies the same cut to every year it replays, against that
year's actual balances. A schedule is sized on one return path; replayed in a
Monte Carlo scenario where markets fell, the same dollar amount can take money
that year needed, and the shortfall would be charged to the policy instead of
the market. A year that would run short converts only what it can spare
(nothing below the minimum); the ledger records the amount actually converted.
Only a short year pays for the extra simulations.

The rate-limit check simulates the year at each candidate amount and reads the
rate on the **last dollar** of taxable ordinary income (`_last_dollar_rate`,
the bracket's upper edge belonging to that bracket), so spending withdrawals,
taxable Social Security and the senior deduction all count. It is the last
dollar, not the next one after it: those differ exactly when a conversion fills
a bracket to its edge — where `marginal_rate` reports the *next* bracket's
rate — so screening on the next dollar would make a 12% cap reject the very
conversion that fills the 12% bracket. A year whose spending withdrawal alone
passes the cap allows no conversion at all.

---

## 2. Policy construction — `search.py`

A *candidate* is one year's amount. A *policy* is a whole-horizon schedule.
Four families:

**The baseline.** `none` — an all-zero schedule, registered first so it owns
that id. `run_optimization` uses it as the counterfactual for BETR, the
marginal-cost rate, and the projected future marginal rate, so it must
genuinely never convert.

**Bracket-fill rules.** `_ANNUAL_RULE_IDS` = `fill_10/12/22/24/32`. Each
walks the **entire horizon**, taking that rule's amount every year it is
offered. Suffixed `_annual`. These are the interpretable "fill the 22% bracket
every year" strategies, and they are the ones that resemble a hand-built
spreadsheet.

**Level-dollar rules.** `_LEVEL_RULES` = `level_5pct/10pct/20pct`: one fixed
dollar amount, sized once as 5%, 10% or 20% of the *starting* traditional
balance (the shares the year-0 `level_25/50/100` candidates take), converted
every allowed year. Also suffixed `_annual`. They say "convert about $90,000 a
year", an amount between two brackets that no fill rule can express. The
amount goes through `generate_conversions(requested=…)`, so the year's caps,
affordability cut and IRMAA / marginal-rate filters apply exactly as to any
candidate: it is a requested maximum, and the label says "up to".

**Limited-duration rules.** For each `_annual` rule that converts, the same
rule applied through year N and never again — "convert hard for a few years,
then stop". Named `<rule>_thru_<YYYY>`, YYYY being the last year that applies
the rule. A rule's amount in a year depends only on that year's state, which
depends only on earlier conversions, so each variant is exactly a prefix of the
`_annual` schedule followed by zeros; no re-walk is needed. Every `_annual`
rule is registered before any variant, so a schedule two policies share keeps
the full rule's name. `rule_of(policy_id)` returns the rule (`fill_22`,
`level_5pct`) for every policy but `none`. Monte Carlo scores every policy
(§4).

Policies are deduplicated on their trailing-zero-trimmed schedule, so a
variant that only adds a zero year collapses into the one before it.

**Greedy rollouts (removed October 2026).** The search used to build a
fourth family: fix a year-0 candidate, then pick each of years 1–4 as the
candidate maximising the remaining horizon. A benchmark gate on seven cases
showed that the rules above — once the level-dollar family was added — score
within max($5,000, 0.25% of investable assets) of the best greedy plan, with
success within 1 point, so greedy was removed in favour of strategies that can
be named and repeated. `backend/benchmarks/greedy_reference.py` keeps a
standalone copy so the gate can be re-run ([Benchmarks](#benchmarks)); the
measurements are in the
[history archive](OPTIMIZER_HISTORY.md#the-october-2026-gate-that-removed-greedy-rollouts-16-october-2026).
Older saved runs still carry greedy ids, and the labels keep naming them.

> **A rule schedule stops at the first year it cannot fund.**
> `_build_rule_schedule` breaks out of its walk when a year reports a
> shortfall. That is intentional — there is nothing left to convert — but it
> means anything that produces a *spurious* shortfall silently truncates the
> schedule, and the policy then scored is not the policy its name describes.
> This is exactly what a solver bug did until `06a27cb`: `fill_32_annual` was
> being built as two conversion years instead of four.

### Which policies exist

Which policies exist is a property of the **inputs**, not a fixed menu: each
`_annual` rule walks the whole horizon, a duration variant is added for each
year it converts, and identical schedules collapse into one. A household still
earning a salary may have no room to fill the 12% bracket for years, so
`fill_12_annual` converts nothing until room appears. The standard household
produces 95 policies (97 with Social Security); the walkthrough's other
households produce 43 (a $500k IRA that runs dry), 112 (a $6M IRA) and 76 (a
couple still on salary) — see [How a recommendation is chosen](HOW_A_RECOMMENDATION_IS_CHOSEN.md),
whose tables `backend/benchmarks/walkthrough.py` prints.

---

## 3. Deterministic evaluation — `evaluate.py`

`simulate_path` runs the full horizon on a single expected-return path and
returns:

```
economic_value = PV(terminal estate, heir-adjusted)
path_value     = objective_value(result, settings)
               = economic_value − shortfall_weight · shortfall_pv
                                − discretionary_shortfall_weight · discretionary_shortfall_pv
```

In words, `path_value` is **what the heirs get, in today's dollars, on one
assumed future, less any spending the plan failed to fund**. Taxes are not a
separate term: every tax dollar has already left the accounts, so the estate is
net of it. (Until October 2026 the formula also subtracted PV(lifetime taxes),
counting them twice, and an `estate_weight` priority could zero the estate out
entirely, which rewarded plans with less income.) Both terms are discounted at
`discount_rate` (2%). `objective_value` is the same function Monte Carlo
averages, with the same weights. The objective's history, with a worked
example under the old formula, is in the
[archive](OPTIMIZER_HISTORY.md#worked-path_value-under-the-old-objective-before-october-2026).

`path_value` gives the search a single number to sort on cheaply. The joint
claim-age search uses it to shortlist policies in each claim pair before any
Monte Carlo (§5a); a fixed-age run sends every policy to Monte Carlo (§4). One
path cannot see sequence risk, which is why the decision is never taken on it.

Terminal estate is heir-adjusted: traditional dollars count at
`(1 − heir_tax_rate)`.

`path_value` and the Monte Carlo objective are the same function with the
same weights (until October 2026 the deterministic one charged the
discretionary tier at 1.0 against Monte Carlo's 0.5). Spending shortfalls
reduce the score. The optimizer balances those penalties against the
after-tax estate; it does not rank solely by whether spending was fully
funded. Policies are ranked by score, with success probability used only to
break a tie.

A shortfall no longer ends a path. The horizon is set by the planning age, not
by when the money runs out, and the years after depletion are the ones worth
seeing.

### Defaults that shape every answer

| setting | default | note |
|---|---|---|
| `nominal_return` | 0.06 | |
| `inflation` | 0.03 | never varied by Monte Carlo |
| `discount_rate` | 0.02 | PV discounting |
| `shortfall_weight` | 1.0 | λ — one PV dollar unfunded costs one dollar |
| `discretionary_shortfall_weight` | 0.5 | voluntary guardrail cuts, charged not free |
| `heir_tax_rate` | 0.25 | |
| `min_conversion` | $1,000 | |
| volatility | 0.12 | Monte Carlo only |

`estate_weight` was removed from `Settings` in October 2026. The API still
accepts it and the database still stores it, so older plans load, but it no
longer changes any result; runs carry `"objective":
"pv_estate_minus_weighted_shortfall"` to tell them apart from older runs.

---

## 4. Monte Carlo scores every policy

`run_optimization` hands **every** policy from `search` to Monte Carlo; the
staged budget (§5) is what bounds the cost. Until October 2026 a cut scored
only a shortlist chosen by `path_value`; once the greedy rollouts were gone
every policy was a rule or `none`, so the cut was deleted
([history](OPTIMIZER_HISTORY.md#the-monte-carlo-cut-and-why-it-was-removed-october-2026)).
The cost, measured October 2026: the standard household at 300 runs takes
about 45 s with 95 policies, and the 100-run performance test about 17 s
(budget 25 s local / 40 s CI).

"Every policy enters Monte Carlo" is not "every policy gets the full budget".
The adaptive scorer (§5) still screens on `runs // 3` paths and extends only
its finalists, so production is not equivalent to the benchmark, which scores
every policy on all 300 paths. The runtime increase is the measured price of
broader coverage at fixed claim ages; the joint claim-age search keeps its own
per-scenario screening (top 3 by `path_value` plus `none`) rather than
repeating this across every claim pair.

---

## 5. Monte Carlo scoring — `montecarlo.py`

```
score = mean over paths of objective_value(path)
      = mean of ( PV(heir-adjusted estate)
                  − shortfall_weight · shortfall_pv
                  − discretionary_shortfall_weight · discretionary_shortfall_pv )
```

There is **no variance term**. Standard deviation is symmetric, so it penalised
strategies for occasionally producing a *larger* estate, and the quantity it
was taken over already contained the shortfall charge. `std_value` is still
reported as a diagnostic and never scored.

### Common random numbers

Path *r* is drawn from `Random(seed + r)`, one independent return per simulated
year. Two consequences:

- Every policy sees the **same** sequences, so comparisons are paired and far
  tighter (measured ~3.8× ) than comparing independent means.
- Path *r* is identical no matter how many paths are requested. **Raising the
  budget extends the sample; it does not redraw it.** 500 runs keeps paths
  0–299 byte-identical and appends 200 more.

Independent per-year draws (rather than one return held for the whole horizon)
are what make this a sequence-of-returns model: a bad year is offset by others,
so the horizon average clusters near the mean.

### Staged budget

```
stage1 = max(1, runs // 3)        # 100 at 300 runs, 166 at 500
survivors = 3
```

Every candidate is scored on the stage-1 slice; the top 3 are carried to the
full budget by **appending** paths to the same sample. Eliminated policies are
still reported, with their smaller path count visible, but are ranked strictly
below the finalists **regardless of score** — a policy dropped on 100 paths is
not reinstated by a lucky mean, because it lost on the evidence available and a
noisier estimate is not grounds to bring it back.

Consequence worth knowing: **a policy cut at stage 1 cannot win at any budget.**
The walkthrough's $6M household shows the cut biting: `fill_12_annual` is third
by `path_value` and fifth at stage 1, so only the `fill_22` family is scored on
the full budget ([Example 3](HOW_A_RECOMMENDATION_IS_CHOSEN.md#example-3--a-very-large-ira-and-modest-spending)).

`none` is passed as a **contender**: carried to the full budget whatever its
stage-1 rank, *and* ranked with the finalists on the full sample. So "do
nothing" is always judged on the same evidence as the plans that would replace
it, and can win after full evaluation even when it missed the stage-1 cut
(`test_baseline_no_conversion.py` builds such a case). Until October 2026 it
was ranked by its stage-1 result like any other policy.

A forced run (`policy_id` in the request) passes the pinned policy as `pinned`:
it is carried to the full budget even when stage 1 would have cut it, because
it is reported whatever its rank, but it keeps the place stage 1 gave it.
Every policy's actual count is in the response as `monte_carlo_paths`
(`winning_policy` and each alternative), and the success interval on the
Results page and in the Excel export is computed from it; `monte_carlo_runs`
is the request. Until October 2026 a pinned policy cut at stage 1 kept
`runs // 3` paths while the interval used the full count, so it showed too
narrow.

### Verdicts

`compare_paired` reports `winner` / `alternative` / `unresolved` / `equivalent`.
A decisive call needs the CI to exclude zero **and** the median to share the
mean's sign. Statistical non-significance is not equivalence: `equivalent` is
only returned when the interval fits inside an explicitly declared materiality
threshold. With none declared, the honest answer is `unresolved`. Results pass
`materiality(state)` = max($5,000, 0.25% of investable assets). The page and
exports label the four as *Recommendation ahead*, *Alternative ahead*,
*Too close to distinguish* and *Practically equivalent*
(`frontend/src/lib/verdicts.ts`, `backend/src/reports/result_labels.py`).

### Does the run count change the answer?

Measured both ways — staged (as shipped) and with staging bypassed so every
policy sees the full sample:

| budget | the user's plan (not in the repository) | standard household |
|---|---|---|
| 0 (deterministic) | `fill_12_annual` | `fill_12_annual` |
| 100 | `fill_10_annual` | `fill_12_annual` |
| 300 | `fill_10_annual` | `fill_12_annual` |
| 500 | `fill_10_annual` | `fill_12_annual` |
| 1000 | `fill_10_annual` | `fill_12_annual` |

**The Monte Carlo winner does not move** with the budget. What moves is
`success_probability` — 0.760 → 0.727 → 0.710 → 0.704 on the user's plan,
still drifting at 1000; 0.950 → 0.930 → 0.926 → 0.912 on the standard household. That is
the noisy figure; treat a difference of a point or two between policies as
nothing. 300 runs is enough to pick a policy and not enough to pin a success
probability to the percent. (Measured 15 October 2026, while greedy rollouts
still existed; neither winner was a greedy plan.)

Deterministic and Monte Carlo *can* pick different policies, and that is not a
bug. On the standard household they now agree. On the user's plan,
deterministic picks `fill_12_annual` ($564,438) and MC picks `fill_10_annual`
($184,250): the plan is underfunded on ~27% of paths even converting nothing,
so conversion tax paid early deepens the gap in bad sequences and is charged
at λ = 1.

---

## 5a. The joint claim-age search — `joint.py`

`run_joint_optimization` chooses Social Security claim ages and the conversion
policy together. It runs as a background job (`src/api/jobs.py`: one worker,
in memory, `POST /optimize/jobs` → `GET /optimize/jobs/{id}`; a second request
while one runs gets 409).

```
enumerate_scenarios()       claiming.py     every eligible (self, spouse) claim pair
      │                                     + the entered pair (diagnostic if ineligible)
      ▼
search() per scenario       search.py       each with its own federal-tax memo
      │
      ▼
stage 1, first 50 paths     montecarlo.py   top 3 by path_value + `none` per scenario;
      │                                     EVERY policy at the entered ages (pinned)
      ▼
stage 2, all 300 paths      montecarlo.py   top 5 eligible by stage-1 score, the entered
      │                                     set, `none` at the leading ages
      ▼
winner                                      best fully sampled eligible candidate
      ▼
sensitivity                 search.rebuild_policy  top 3 under horizon −5/+5 and,
      │                                     for a couple under 78, each death at 78
      ▼
build_report()              optimizer.py    yearly plan from the winner's own scenario
```

Eligibility (`claiming.claim_age_options`): ages max(62, today's age) to 70;
locked to the stored age when already receiving; "file now" at the age-70
credit when over 70 and not receiving; and the ages at which that person's (or a
joint) salary is still paid between the claim and full retirement age are
excluded, because the earnings test is not modelled. Exclusions are reported
with their reason, and an entered pair that falls among them is still scored
as a diagnostic but never wins.

Path *r* is `Random(seed + r)` for every candidate in every scenario, so all
comparisons are paired, across scenarios too. Only the entered scenario gets
every policy: multiplying evaluate-every-policy across claim pairs is what the
per-scenario screen exists to avoid. A searched person may have no entered age
(`ss_claim_age_*` NULL: "Find the best eligible age" with no comparison age).
Then there is no entered scenario: nothing is pinned, every scenario is
screened alike, and `baselines` holds only `winner_ages_no_conversion` -- no
"your ages" pair is invented. Every run that holds an age fixed (`/optimize`,
What-if, the policy list, a fixed person in a search) refuses a missing age
with a 422 (`claiming.require_claim_ages`) rather than model no benefit. The result's `search` block carries the
matrix (`scenarios`, each with its stage-1 and, if a finalist, full-sample
best), `stages` (including `winner_stage1_score`, the winner's own score on the
first 50 paths, which the screening comparisons are measured against; older
runs lack it and show the comparison as unavailable), `baselines` (entered ages
with and without conversions when there are entered ages, winner's ages without), `comparisons`,
`exclusions`, `sensitivity` and `materiality`. `alternative_policies` lists the
top 3 fully sampled candidates plus every finalist. With `monte_carlo_runs: 0`
the search is deterministic only and returns `deterministic_matrix` instead.

**Does the 50-path stage 1 promote the right finalists?**
`backend/benchmarks/joint_screening.py` scores every policy in every eligible
scenario on the full sample as a reference and measures two losses: what the
deterministic screen leaves out, and what the 50-path stage 1 then fails to
promote. Acceptance is the gate's materiality and success within 1 point. On
three cases (a private household plan, `widow_A`, `widow_B`) at seeds 42 and
10042 both losses were zero. One end-to-end search on that plan took 199 s with
a 295 MB peak. The benchmark's third case is now the synthetic
`salaried_couple` fixture, so a re-run reports different figures for it.

---

## 6. The per-year engine — `transition.py`

`simulate_year` is the correctness-critical heart and runs ~100,000 times per
optimization. Order: RMD → conversion → spending solve → taxes → balances →
growth.

RMDs are taken **per IRA owner** (`household_rmds`): `State` carries the
spouse's share of the traditional balance, each owner's RMD is their own
balance over the factor for their own age, from their own SECURE 2.0
applicable age, and conversions and withdrawals draw on both IRAs in
proportion. After the first death the survivor owns everything. Ages are the
ones attained in each tax year. Until October 2026 one RMD was taken on the
household total at self's age, so a younger spouse's IRA paid early and an
older spouse's owed RMD was never taken.

### The funding fixed point

Spending is **after-tax**. Withdrawing more triggers more tax, which requires
withdrawing more, so the year is solved as a fixed point:

```python
tax_estimate = 0
for _ in range(_FUNDING_SOLVE_MAX_ITERATIONS):
    need = required_spending − (fixed_cash + rmd) + tax_estimate
    w = _solve(need)                      # taxable → traditional → roth
    new_tax = federal + state + irmaa
    if abs(new_tax − tax_estimate) < $0.01:
        break
    tax_estimate = new_tax
```

### How it converges

This is **Picard iteration** — repeatedly substituting an estimate back into
the relation that defines it — and it converges because the map is a
contraction. Its factor is the effective marginal rate `r` on the funding
dollar: raising the withdrawal by `Δ` raises the tax by `r·Δ`, so the error
left after each pass is `r` times the error before it.

```
eₙ = rⁿ · e₀                      ⟹     n ≥ log(ε / e₀) / log(r)
```

`e₀` is the **whole tax bill**, because `tax_estimate` starts at zero, and
`ε` is the $0.01 the loop exits on. Both terms matter: a large conversion
raises `e₀`, and exhausting the taxable account mid-solve switches the marginal
dollar from capital-gains rates to ordinary rates, raising `r`.

The cap, `_FUNDING_SOLVE_MAX_ITERATIONS`, is **60**. The worst year measured
(September 2026) needed 26 passes (`fill_32_annual` on the standard household, where `r ≈ 0.443`
once funding switches to the IRA), so the cap leaves about 2.3× headroom; the
early exit means a year that converges in two passes still takes two. A cap
of 12 used to truncate rule schedules by reporting the unconverged residue as
a shortfall — see the
[archive](OPTIMIZER_HISTORY.md#the-funding-solver-iteration-cap-september-2026-06a27cb).
A property test asserts the invariant directly: a shortfall may only be
reported when the accounts actually ran dry.

This is **not** a widened tolerance. `_FUNDING_TOLERANCE` stays at $1. Widening
it would hide a solver failure behind an accounting threshold, and no value
could be justified — the residual is `rⁿ · e₀`, a function of the marginal
rate and the tax bill, not a constant.

> **`feasible` is still a knife-edge.** It has no materiality threshold, so a
> plan that misses by one dollar in one year scores the same success
> probability as one that runs out at 71. Full convergence removes the known
> cause of spurious misses; whether "success" should tolerate a trivial gap is
> a separate design question, deliberately left open.

### Where surplus cash goes

The mirror of a shortfall is a **surplus**: cash income (salary, a pension,
or an RMD larger than the spending) that the year neither spends nor pays in
tax. It is deposited in the taxable account **at full basis** (it is cash, so
selling it later realizes no gain), before that year's growth, and reported as
`surplus_saved` in the tax audit. The same $1 residue floor applies as for the
shortfall.

Until October 2026 the surplus was dropped, which made converting look free in
surplus years ([archive](OPTIMIZER_HISTORY.md#surplus-cash-before-october-2026)).
A property test asserts that, with zero growth, household wealth changes only
by cash income, tax and spending.

---

## 7. Verifying the numbers

**Per-year identities**, checkable in any exported row (each to within $1, the
funding solver's tolerance):

- `cash income + RMD + spending withdrawals − total tax = required spending + surplus saved − shortfall`,
  where cash income is salary, pension, rental income, the whole Social
  Security benefit, interest and dividends, and spending withdrawals are the
  taxable, traditional and Roth withdrawals made to fund the year. Roth
  conversions are **not** spending withdrawals: they move money between
  accounts and appear only through their tax. In a funded year without a
  surplus, the right side is simply the required spending.
- `federal + state + IRMAA = total tax`
- the ordinary-income lines sum to the ordinary-income total

**The Tax Audit sheet** (Excel export) carries the full derivation per year.
For a bracket-fill recommendation the line that matters is
**"— of which taxable ordinary income"**: a bracket's edge bounds ordinary
income, so `Taxable income` — which also contains qualified dividends and
long-term gains — cannot verify a fill. In TY2026 the married-joint 12% top is
$100,800; a correct `fill_12` year lands exactly there.

**The Bracket Room column** on the Results year table (and `bracket_rate` /
`bracket_room_left` in the CSV and Excel exports) is the quick check: a
correct `fill_NN` year shows *"$0 left in NN%"*, with the next bracket's rate
under Marginal %. It is measured on taxable ordinary income, the same quantity
as the Tax Audit line above.

**Invariants on random households** — `tests/property/test_household_invariants.py`
generates hundreds of households (filing status, ages, balances, salary,
pension, Social Security, dividends, state, spending, bracket cap, withdrawal
order) and checks what must hold for all of them: a fill lands at or below its
bracket, nothing the cap allows lands above it, every year funds its spending
unless the accounts are empty, RMDs and the pre-RMD window follow the SECURE
2.0 age, and conversions never exceed the IRA. Examples are derandomized,
so a failure reproduces exactly. It runs in about a minute and a half.

<a id="benchmarks"></a>**Benchmarks** — reproducible from `backend/`:

```
uv run python -m benchmarks.greedy_vs_rules --paths 300 --seed 42 --out gvr.json --gate
uv run python -m benchmarks.joint_screening --seeds 42 10042 --out /tmp/joint_screening.json
```

`greedy_vs_rules` scores every production policy plus the retired greedy
rollouts on the same paths and applies the removal gate (re-run it when the
rule families or the objective change). `joint_screening` measures what the
claim-age search's screening leaves out (§5a). A confirmation seed must differ
from the gate seed by at least the path count: path *r* is `Random(seed + r)`,
so seeds 42 and 43 share 299 of 300 paths.

**Reproducing a run** — `backend/benchmarks/walkthrough.py` runs `search` and
`score_policies_adaptive` one stage at a time on four fixed households (and the
first as a claim-age search) and prints every table in
[How a recommendation is chosen](HOW_A_RECOMMENDATION_IS_CHOSEN.md): the rule
walks and why a rule produced nothing, the `path_value` ranking, the stage-1
means, the finalists and their paired verdicts. `--out` writes every number as
JSON. `tests/unit/test_walkthrough_cases.py` guards the properties each example
illustrates. The golden fixture (`tests/integration/golden_standard_household.json`)
is the regression anchor for the standard household; compare before ever
regenerating it.

**Against your own spreadsheet** — see
[`VERIFYING_RESULTS.md` → Reconciling against your own spreadsheet](VERIFYING_RESULTS.md#reconciling-against-your-own-spreadsheet).
The short version: turn the simulation off, pin the same strategy, clear the
bracket cap, and compare taxable ordinary income rather than conversion
dollars.

---

## 8. Known characteristics

Not bugs; consequences of documented choices. Each changes numbers a reader
might otherwise expect to match another tool.

- **Tax tables past the latest published year are projected**
  (`data/tax_rules/indexing.py`) at the plan's inflation, floored at zero, from
  the latest published table with one factor: federal brackets and LTCG
  thresholds (rounded down to $25), the standard deduction and age-65 addition
  ($50), IRMAA thresholds ($1,000; the $500k/$750k top tier frozen through
  2027), and California's ordinary brackets and deduction ($1). Not indexed:
  NIIT and Social Security taxation thresholds (statutory), the senior bonus
  (2025–2028 only), SALT (its enacted schedule, $10,000 from 2030), IRMAA
  premium dollars, California's $1M mental-health surcharge threshold, and
  every other state's brackets. Conversion sizing and IRMAA checks read the
  same projected tables the tax engines use; a year's MAGI is judged against
  the premium year two ahead. Before October 2026 every table was frozen at its
  last published year, which overstated far-future tax.
- **Social Security grows by a COLA** — `Settings.ss_cola`, defaulting to the
  plan's inflation floored at zero. PIAs are start-year dollars and are indexed
  from the start year before claiming as well as after, before the
  calculator's reductions, credits and rounding. Before October 2026 benefits
  were flat in nominal terms.
- **The spousal benefit is applied** — a spouse's own benefit plus the excess
  of 50% of the higher earner's PIA over their own unreduced PIA, from the
  year the higher earner files (SSA dual entitlement, POMS RS 00615.020). The
  excess is reduced for the months before FRA at which that top-up began, not
  at the spouse's own claim. Many hand-built models omit this.
- **Full retirement age follows the birth year** (`data/tax_rules/social_security.py`):
  67 for 1960 and later, 66 and 2–10 months for 1955–1959, with SSA's
  separate, two-years-later table for survivor benefits. Until October 2026
  every benefit assumed 67. SSA's rule that a 1 January birthday counts as the
  previous year is not modelled — only the birth year is stored.
- **A conversion is capped at what the year can spare** (`_affordable_conversion`,
  §1): spending draws on the Roth balance from the start of the year, so
  converted dollars cannot fund the same year's spending. On a small IRA with no
  taxable account behind it, the bracket fills are cut back rather than
  creating a shortfall.
- **BETR's horizon runs to the owner's RMD age** (73 or 75 by birth year),
  via `rationale/generator._years_to_rmds`. BETR is a diagnostic only.
- **The first two IRMAA years use a MAGI proxy** (salary + pension + rental +
  interest + Social Security + ordinary dividends); no historical AGI is
  stored.
- **Capital gains already realized, and loss carryovers** (`engines/tax/capital_gains.py`).
  The household may enter the net short- and long-term result of sales made
  earlier in the plan's first year and the loss carried into it
  (`CapitalGainsIn`, stored as `settings.capital_gains_json`, applied only when
  its `tax_year` is the first year; an older one is reported as not applied).
  They are tax figures, never cash. Each year nets them with the long-term gain
  of its own sales as Schedule D does: a net short-term gain is ordinary income,
  a net long-term gain goes to the capital-gains schedule, a net loss is
  deducted up to $3,000 and the rest carries forward with its character
  (`State.loss_carryover_st/lt`), counting only the deduction that had taxable
  income to offset. The state follows one of three treatments
  (`STATE_CAPITAL_LOSS_RULES`): `federal` (the default, e.g. NY) keeps the
  federal netting and carryover; `separate` (CA, WI) nets again with a $3,000
  limit and figures `State.state_loss_carryover_st/lt` on state gross income
  less the state deduction; `none` (PA, NJ) nets same-year gains only, with no
  deduction against other income and no carryover.
  `_baseline_income` includes the entered figures but not
  the year's own sales; adding long-term gain never lowers the ordinary part
  of a netted result, so the closed-form bracket room stays an upper bound.
- **The plan's own sales never realize a loss.** A taxable account whose basis
  exceeds its value is allowed; a sale from it realizes no gain, and no loss
  either (the aggregate basis cannot say which lots are sold; a negative gain
  would also break the upper bound above) — a conservative bias.
- **Monte Carlo varies only the annual return.** Inflation, spending, Social
  Security and longevity are never varied.
- **IRMAA policies.** The surcharge is charged for each person on Medicare
  under every policy (`_compute_taxes`); the policy only constrains
  conversions. `ignore` and `soft` are the same rule (cost only), and so are
  `strict` and `avoid` (drop a conversion whose simulated MAGI crosses the next
  tier, `_TIER_POLICIES`). Until October 2026 `ignore` charged nothing, only
  self's Medicare status triggered a charge, `strict` behaved like `soft`, and
  `avoid` judged baseline MAGI + conversion, which the gains realized to pay
  the conversion's tax could push over the tier.
- **Deterministic mode is only reachable from the What-if page.** The main
  Results page calls `optimize()` with no run count and takes the default of
  300 (`frontend/src/app/page.tsx`, `frontend/src/lib/api.ts`).
