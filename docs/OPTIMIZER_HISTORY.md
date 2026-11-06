# Optimizer history (archive)

A dated record of how the optimizer reached its current form, September–October
2026. **Nothing here describes the current code.** Figures were measured on the
code of the day stated in each section, several of them before the October 2026
corrections or while greedy rollouts still existed, and they are kept as the
evidence behind decisions, not as expected outputs. For how the optimizer works
now, see [Optimizer internals](OPTIMIZER_INTERNALS.md).

Unless stated otherwise the household is the standard test household described
at the top of that document.

---

## The 16 policies on the standard household (greedy era, measured 15 October 2026)

Before greedy rollouts were removed, `search` produced 16 policies on this
household: `none`, the five `_annual` fill rules, and ten greedy rollouts (each
fixing a year-0 action and re-choosing years 1–4). The first five by
`path_value` reached Monte Carlo, plus every `_annual` rule and `none`. The
table was measured after the October corrections (surplus cash saved, the
age-65 standard deduction applied) but **under the old objective**, which still
subtracted PV(lifetime taxes) from the estate.

Each row is one complete 30-year schedule, simulated once on the expected 6%
path. The columns:

- **conversion years** — how many years of that schedule convert anything at
  all (non-zero entries). It is *not* the policy's length: every policy is
  simulated for the full horizon, most years just convert $0.
- **total converted** — the nominal sum of those conversions, in the dollars of
  the year each happens.
- **path_value** — the ranking number, in present-value dollars. Higher is
  better. On this household no policy runs short, so it is simply
  `PV(heir-adjusted estate) − PV(lifetime taxes)`.

| # | policy | family | conversion years | total converted | PV taxes | path_value | → MC |
|---:|---|---|---:|---:|---:|---:|:---:|
| 1 | `fill_12_annual` | rule | 10 | $574,466 | $739,373 | $2,452,792 | ✓ |
| 2 | `level_50` | greedy | 4 | $635,759 | $730,452 | $2,411,656 | ✓ |
| 3 | `fill_24` | greedy | 4 | $671,394 | $744,615 | $2,394,959 | ✓ |
| 4 | `fill_12` | greedy | 4 | $632,113 | $740,217 | $2,376,393 | ✓ |
| 5 | `level_25` | greedy | 4 | $648,513 | $748,791 | $2,361,843 | ✓ |
| 6 | `level_100` | greedy | 4 | $631,053 | $754,163 | $2,337,210 | |
| 7 | `fill_32` | greedy | 3 | $632,550 | $755,325 | $2,334,636 | |
| 8 | `fill_22` | greedy | 4 | $642,552 | $758,650 | $2,329,280 | |
| 9 | `max_pre_rmd` | greedy | 3 | $660,023 | $767,134 | $2,315,126 | |
| 10 | `fill_10` | greedy | 3 | $643,000 | $772,959 | $2,277,618 | |
| 11 | `defer_1yr` | greedy | 2 | $633,000 | $777,968 | $2,252,984 | |
| 12 | `fill_10_annual` | rule | 6 | $182,250 | $858,977 | $2,189,827 | ✓ |
| 13 | `fill_22_annual` | rule | 19 | $1,831,748 | $857,708 | $2,008,328 | ✓ |
| 14 | `none` | baseline | 0 | $0 | $932,539 | $1,989,979 | ✓ |
| 15 | `fill_24_annual` | rule | 8 | $2,042,558 | $883,834 | $1,547,371 | ✓ |
| 16 | `fill_32_annual` | rule | 6 | $2,077,598 | $914,567 | $1,346,900 | ✓ |

Reading the counts:

- **The greedy rows show 2–4 years** because a greedy policy can only convert
  inside the 5-year lookahead window, and the greedy step usually stops
  converting before the window ends. `fill_24` is `$396k, $158k, $103k, $15k` in
  2025–2028. Its name describes year 0 only; years 1–4 are re-chosen.
- **The greedy totals all land between $631k and $671k** whatever the year-0
  action, because the later greedy years compensate: `fill_12` converts $98k in
  year 0 and then $406k in year 1, `level_100` converts $500k and then $103k.
- **The rule rows run until they cannot.** This household's taxable account is
  used up in 2030 under `fill_12_annual` (2031 converting nothing, 2028 under the
  heavy converters), after which its spending comes out of the IRA, and that
  withdrawal is ordinary income in the same brackets. It fills most of the 10%
  and 12% brackets by itself: `fill_10_annual` stops after 2030 and
  `fill_12_annual`, which converts about $100k a year for five years, tapers to
  a few thousand dollars a year and stops after 2034. `fill_22_annual` keeps
  finding room for 19 years; `fill_24_annual` and `fill_32_annual` convert
  $150k–$500k a year and have all but emptied the IRA within 8 and 6.

The modest rule, `fill_12_annual`, now ranks **first**; the heavy rules still
sit near the bottom. They convert **about 3× as much** and pay tax every year
for years, so their PV taxes run $80k–$185k above the greedy policies, and on
one expected-return path nothing pays that back. Before the October
corrections `fill_12_annual` ranked tenth: the cash a light converter's RMDs
produce beyond its spending was being dropped, and a heavy conversion's tax
came out of cash that was about to vanish anyway, so converting heavily looked
cheaper than it is (see *Surplus cash before October 2026* below).

Until `10bcfa5` the rule rows ignored that IRA spending withdrawal when sizing a
fill, so `fill_12_annual` converted $103,000 a year from 2030 and landed in the
24% bracket (26 conversion years, $1.71M in all). See [Optimizer internals](OPTIMIZER_INTERNALS.md#bracket-sizing-is-not-bracketupper--taxable_income).

---

## The October 2026 gate that removed greedy rollouts (16 October 2026)

`backend/benchmarks/greedy_vs_rules.py` scores every policy (the production
search's policies plus the greedy reference) on the same 300 paths, seed 42,
for seven cases: the standard household, the widow fixture (A: both live to
the entered ages; B: the spouse dies at 78) and the user's four plans (which
differ only in nickname, so they are one case in effect). That private fixture
has since been replaced by the synthetic `salaried_couple`, so a re-run reports
different figures for it. The written rule for
removing greedy: in every case the best non-greedy score is within
max($5,000, 0.25% of investable assets) of the best score, and its success
probability within 1 point.

**First run, fill rules and their duration variants only: FAIL.**

| case | best overall | best non-greedy | gap | tolerance |
|---|---|---|---|---|
| standard | `fill_12_thru_2043` $3,546,642 | same | $0 | $7,375 |
| widow A | `level_25` (greedy) $2,358,032 | `fill_10_annual` $2,343,012 | $15,019 | $6,250 |
| widow B | `level_25` (greedy) $1,668,259 | `fill_12_thru_2043` $1,659,153 | $9,105 | $6,250 |
| user plans | `none` $2,613,605 | same | $0 | $6,250 |

The widow gaps were real (paired 95% intervals [$12,625, $17,414] and
[$6,776, $11,434]). What no fill rule expressed was a **level dollar amount
between two brackets**: greedy `level_25` converts about $90,000 a year for
three or four years, where the fill rules size to $57,000 (`fill_10`) or
$133,000 (`fill_12`). Stopping early did not close it: `fill_12_thru_2043`
gains $214 over `fill_12_annual`. (The 2026-10-16 experiment's $74,000 widow-B
gap, measured before the COLA, objective and tax-indexing corrections, was
already down to $9,105.)

**Second run, with the level-dollar family added once (5/10/20% of the
starting IRA, the existing greedy seed shares, not tuned): PASS.**

| case | best overall | best non-greedy | gap | tolerance | Δ success |
|---|---|---|---|---|---|
| standard | `fill_12_thru_2043` $3,546,642 | same | $0 | $7,375 | 0 |
| widow A | `level_25` (greedy) $2,358,032 | `level_5pct_thru_2029` $2,352,370 | $5,662 | $6,250 | −0.3 pt |
| widow B | `level_25` (greedy) $1,668,259 | `level_5pct_thru_2029` $1,666,587 | $1,672 | $6,250 | 0 |
| user plans | `none` $2,613,605 | same | $0 | $6,250 | 0 |

Checks that went with it:

- **Screening.** The joint claim-age search carries the top 3 by path_value
  plus `none` per scenario. That shortlist kept the non-greedy winner in every
  case (loss $0, $236 on the standard household), so the gate holds after
  screening. A one-per-rule diversity cap made it worse (widow A lost $1,929
  and failed), so none is used. This shows only that top-3-plus-`none`
  *contains* the winner when every candidate is then scored on all 300 paths.
  Whether the joint search's 50-path stage 1 then promotes the right finalists
  is measured separately, by `backend/benchmarks/joint_screening.py` ([Optimizer internals](OPTIMIZER_INTERNALS.md#5a-the-joint-claim-age-search--jointpy)).
- **A non-overlapping seed.** Path *r* is drawn from `Random(seed + r)`, so
  seeds 42 and 43 share 299 of their 300 paths, and an early seed-43 check
  ($5,640 and $1,668, within $20 of seed 42) was not independent. On paths
  10042–10341, which share none with seed 42, greedy `level_25` leads
  `level_5pct_thru_2029` by $3,289 (widow A, paired 95% interval
  [$894, $5,684]) and $1,406 (widow B, [$1,122, $1,690]), both inside the
  $6,250 tolerance, with success about −0.3 point and unchanged. Greedy is
  still slightly better; the simpler family meets the replacement standard.
  A confirmation seed must differ from the gate seed by at least the path
  count.
- **Runtime**, one 300-run optimize: standard 34 s with greedy and no level
  rules, 48 s with both, 45 s with level rules and no greedy (95 policies);
  widow 33–35 s → 41–43 s; the user's plan 17 s → 28 s (25 policies).

So greedy was removed, and Monte Carlo then scored every policy (see the next section).

The benchmark is still runnable; see
[Optimizer internals → Benchmarks](OPTIMIZER_INTERNALS.md#benchmarks).

---

## The Monte Carlo cut and why it was removed (October 2026)

Until October 2026 a cut, `_monte_carlo_candidates`, scored only the top 5 by
`path_value` plus every `_annual` rule and `none`, and later every
`_thru_<YYYY>` variant too. A shortlist property test (since removed with the
cut) found a household the cut failed: a single 78-year-old with a $2.6M IRA,
where Monte Carlo over every policy picks `fill_24_thru_2027` (two years, then
stop) decisively while `path_value` ranked it ninth and the shortlist picked
`none`. Once the greedy rollouts were gone every policy was a rule or `none`, so
the cut kept nothing out and was deleted.

The rest of this section is from the cut's era and explains the bias that
made every extra necessary.

The extras exist because the cut ranks on `path_value` — one deterministic
path — while the decision is taken on the Monte Carlo average, and the two can
disagree in a predictable direction: the rules pay tax every year for years,
which a smooth path never pays back. Scoring all 16 on the same 300 paths:

| MC rank | policy | MC score | success | path_value rank |
|---:|---|---:|---:|---:|
| 1 | `fill_12_annual` | 2,314,487 | 93.0% | 1 |
| 2 | `fill_24` | 2,295,721 | 92.3% | 3 |
| 3 | `level_50` | 2,279,457 | 92.3% | 2 |

On today's code the two rankings **agree** for this household: the same plan
is first on both. Measured winners and Monte Carlo time (300 runs) by
candidate set:

| set | standard household | `user_test` plan | MC time (standard) |
|---|---|---|---:|
| top 5 | `fill_12_annual` | `fill_10_annual` | 7.1s |
| top 5 + best rule by path_value + `none` | `fill_12_annual` | `fill_10_annual` | 7.5s |
| top 5 + every rule + `none` (**shipped**) | `fill_12_annual` | `fill_10_annual` | 10.0s |
| all 16 | `fill_12_annual` | `fill_10_annual` | 15.0s |

**Why every rule, not just the best one.** Before the October 2026
corrections this household is where the rankings disagreed: `path_value` put
`fill_24` first and every rule near the bottom, while scoring all 16 put
`fill_22_annual` first — twelfth on `path_value`, so a top-5 cut never scored
it. The first fix carried only the rule `path_value` ranks highest; after the
IRA-withdrawal bracket fix (`10bcfa5`) that was `fill_12_annual` while Monte
Carlo preferred `fill_22_annual`, so the winner was again never scored.
`path_value` can misrank the rules among themselves as well as against the
greedy plans, and there are at most five of them, so all are carried. `none`
is carried for a different reason: "do nothing" has to be beaten in the ranking
that decides, not only in the one that pre-filters. Today the extras change
nothing on this household; they are the insurance for households where the
two rankings still part.

**The winner is decisive.** The paired test — the precise one, since both
policies see identical return sequences — returns `winner` against every
finalist:

```
fill_12_annual vs fill_24     mean +18,766   median +61,126   CI [4,328, 33,204]
fill_12_annual vs level_50    mean +35,030   median +56,130   CI [24,632, 45,428]
fill_12_annual vs level_25    mean +68,030   median +86,040   CI [46,204, 89,855]   (100 paths: cut at stage 1)
```

Each interval excludes zero and the median agrees with the mean. On the single
expected-return path shown in the Alternatives table, `fill_24` pays $5,242
more PV tax and leaves $95,261 less estate; `level_50` pays $8,921 less PV tax
but leaves $90,670 less estate. This year's conversion is therefore one number,
**$98,450**, and the Results page shows no year-0 spread note. Before the
October corrections the same household was *too close to call* — `fill_22_annual`
against `fill_24`, `fill_32` and `max_pre_rmd`, each winning the median path —
and the spread note read $208,200 to $502,550.

What carrying the rules fixes is the selection bias, not the noise: the
pre-filter no longer removes, by construction, the family that the deciding
criterion may favour.

---

## Worked `path_value` under the old objective (before October 2026)

Until October 2026 the objective also subtracted PV(lifetime taxes), counting
them twice (every tax dollar has already left the estate), and an
`estate_weight` priority could zero the estate out entirely. The standard
household's `fill_12_annual` under that formula:

```
PV(heir-adjusted estate)   3,192,165
− PV(lifetime taxes)         739,373   (old formula; no longer subtracted)
− shortfall                        0
= path_value               2,452,792
```

---

## The funding-solver iteration cap (September 2026, `06a27cb`)

Instrumented on a failing year of the standard household when the cap was
raised; the figures are from that code.

```
iter  3   212,561.47   +15,868.50
iter  4   220,384.64    +7,823.17   ratio 0.493
iter  5   223,864.58    +3,479.94   ratio 0.445
...
iter 12   226,623.02       +11.65   ratio 0.443   ← old cap
```

`r = 0.443` is the federal-plus-California marginal rate once funding has
switched to the IRA. With `e₀ ≈ 226,623` the formula predicts
`log(0.01/226623)/log(0.443) ≈ 21` passes. **Measured: 26.** The estimate runs
low because `r` is not constant over the first few passes (0.493 before it
settles), so treat the formula as a floor and the measurement as the answer.

The cap was 12. The last delta it never delivered — $11.65 — surfaced as a
shortfall in a year with millions still in the accounts.

Passes used across a full 30-year horizon after raising the cap to 60:

| policy | min | median | max | final residual | years reporting a shortfall |
|---|---:|---:|---:|---:|---:|
| `fill_32_annual` (large conversion every year) | 2 | 2 | **26** | $0.0000 | 0 |
| `fill_24` (greedy, ordinary) | 5 | 14 | 15 | $0.0000 | 0 |
| `none` (no conversions at all) | 2 | 2 | 13 | $0.0000 | 0 |

Every year now converges fully — the residual reaches $0.0000, not merely
"under tolerance" — and no year reports a spurious shortfall.

**The old cap was binding far more widely than the visible symptom suggested.**
`fill_24` needed more than 12 passes in **21 of its 30 years**, and even `none`
needed 13 in two of them. Those never surfaced as shortfalls because reaching
$1 takes fewer passes than reaching $0.01, so the leftover stayed under
`_FUNDING_TOLERANCE` and was silently absorbed. It was still error: it is why
regenerating the golden fixture after the fix moved terminal estate by $1 on a
policy whose conversions and taxes did not change at all.

So the correction is not only to the pathological years. Those were the ones
loud enough to notice.

The early exit is unchanged, so a year that converges in two passes still takes
two. Measured cost of the higher cap on a 300-path run: **under 3%**.

This is **not** a widened tolerance. `_FUNDING_TOLERANCE` stays at $1. Widening
it would have hidden a solver failure behind an accounting threshold, and no
value could be justified — the residual is `rⁿ · e₀`, a function of the
marginal rate and the tax bill, not a constant.

### Why it mattered more than a wrong card

The residual was reported as `shortfall`. Three things read that:

1. `evaluate.py` flips `feasible` on **any** shortfall above zero, so one $12
   year condemned the whole path, on every path. `fill_32_annual` reported
   **0.0%** success where it is really **83.3%**.
2. `_build_rule_schedule` breaks at the first short year, so the schedule was
   **truncated** — `fill_32_annual` was built as 2 conversion years, not 4.
3. The score therefore described a policy that did not match its own name, and
   the rankings were wrong as a result.

Fixed in `06a27cb`, with a property test asserting the invariant directly: a
shortfall may only be reported when the accounts actually ran dry.

---

## Surplus cash before October 2026

Until October 2026 the surplus was simply dropped. That biased every result
toward converting, in two ways. Under no conversions the standard household's
RMDs exceed its spending from 2036 by **$32k–$81k a year**, and all of it vanished, so `none` scored a
path value of $0.96M instead of $1.96M. And in a surplus year a conversion's
tax came out of cash that was about to vanish anyway, so converting looked
free. A property test now asserts that, with zero growth, household wealth
changes only by cash income, tax and spending. With the surplus kept, `none`
scored a path value of $1.99M on 15 October 2026 (the 16-policy table above), and the
recommendation for this household moved from a too-close-to-call `fill_22_annual`
to a decisive `fill_12_annual` (the Monte Carlo cut section above).

---

## Measurements moved out of code comments (26 October 2026)

These were explanations in the source. The code now keeps the invariant they
justify and points here.

- **Staged Monte Carlo budget** (`optimizer.py`). On a 14-policy household,
  scoring every candidate on a slice and extending only the contenders gave the
  same winner and runner-up as flat scoring at the same budget, for 2,000
  simulated paths instead of 4,200. That saving made 300 runs affordable as the
  default: at 100 runs the success probability carried about ±9 points and
  moved 6–8 points on the seed alone.
- **No variance term** (`montecarlo.py`). Subtracting k·std from the mean once
  decided the recommendation: it turned a plan converting $769,663 into one
  converting nothing, because the standard deviation of the penalised value ran
  about $987,000, the same order as the entire tax signal.
- **Shortfall weights in `path_value`** (`evaluate.py`). The steady-return value
  once charged both shortfall tiers at 1.0 while Monte Carlo charged the
  discretionary tier at 0.5, one avoidable source of the two rankings
  disagreeing. Both now use the same weights.
- **The funding-solver cap** (`transition.py`). Over a full 30-year horizon,
  `fill_24` needed more than 12 passes in 21 of its 30 years and even `none`
  needed 13 in two of them; those stayed silent only because reaching $1 takes
  fewer passes than reaching $0.01. It is why the golden fixture's terminal
  estate moved by $1 when the cap was raised. Raising it cost under 3% on a
  300-path run. The rest is in [The funding-solver iteration
  cap](#the-funding-solver-iteration-cap-september-2026-06a27cb).
