# How a recommendation is chosen

A walkthrough of what the optimizer actually does between your inputs and the
strategy it recommends: which strategies it builds, why some of them never
appear, which ones reach the market simulation, and how the winner is picked.
Four example households are followed through every step, with the numbers the
app produces for them. The [User Guide](USER_GUIDE.md) explains how to read a
result; [Optimizer internals](OPTIMIZER_INTERNALS.md) is the code-level account.

Every figure here was produced on 21 October 2026 by
`backend/benchmarks/walkthrough.py` (see [Reproducing these tables](#reproducing-these-tables)).
The figures change when the engine, the search or a tax table changes; the
steps do not.

## Contents

1. [Three words](#three-words)
2. [The menu of strategies](#the-menu-of-strategies)
3. [Stop-year variants](#stop-year-variants)
4. [What makes a strategy shrink or disappear](#what-makes-a-strategy-shrink-or-disappear)
5. [The steps at fixed claim ages](#the-steps-at-fixed-claim-ages)
6. [Example 1 — a comfortably funded couple](#example-1--a-comfortably-funded-couple)
7. [Example 2 — a small IRA and a tight budget](#example-2--a-small-ira-and-a-tight-budget)
8. [Example 3 — a very large IRA and modest spending](#example-3--a-very-large-ira-and-modest-spending)
9. [Example 4 — still working](#example-4--still-working)
10. [When claim ages are searched too](#when-claim-ages-are-searched-too)
11. [What the search cannot find](#what-the-search-cannot-find)
12. [Reproducing these tables](#reproducing-these-tables)

---

## Three words

**Strategy.** A complete year-by-year schedule of Roth conversions for the
whole plan — one dollar amount for every year, most of them often zero. *Fill
the 12% bracket every year* is a strategy; so is *fill the 12% bracket through
2029, then stop*; so is *no conversions*. A strategy is always simulated to the
last year of your plan, whether or not it has stopped converting.

**Stop-year variant.** A strategy that applies a rule through a given year and
never again. The search builds one for every year a rule converts in.

**Market scenario.** One possible sequence of yearly investment returns over
your plan, drawn around your assumed average return. Every strategy is run
through the same scenarios, so two strategies are always compared on identical
markets.

Two numbers recur. The **steady-return value** is a strategy's result if
investments earned exactly your assumed return every year: the after-tax
estate at the end of the plan, in today's dollars, minus any spending the plan
could not fund. The **modeled score** is the same measure averaged across
market scenarios. The recommendation is chosen on the modeled score.

---

## The menu of strategies

The search starts from nine strategies. Eight apply a rule every year the rule
allows it; the ninth converts nothing.

| # | Strategy | What it does each year |
|---:|---|---|
| 1 | No conversions | Leaves the traditional accounts alone. Always included; it is the baseline every other strategy is compared with. |
| 2–6 | Fill the 10%, 12%, 22%, 24% or 32% bracket | Converts the amount that brings **taxable ordinary income** up to the top of that federal bracket — after your other income, Social Security, RMDs and any spending drawn from the IRA have used part of it. |
| 7–9 | Convert up to 5%, 10% or 20% of the starting traditional balance | Converts one fixed dollar amount, sized **once** from the balance at the start of the plan. |

The fixed amounts in dollars, for the four households below:

| Starting traditional balance | 5% | 10% | 20% |
|---:|---:|---:|---:|
| $500,000 | $25,000 | $50,000 | $100,000 |
| $1,000,000 | $50,000 | $100,000 | $200,000 |
| $2,500,000 | $125,000 | $250,000 | $500,000 |
| $6,000,000 | $300,000 | $600,000 | $1,200,000 |

Points that are easy to get wrong:

- Every amount is a **requested maximum**. The year's caps, your bracket
  limit, the Medicare-surcharge setting and the money the year needs for
  spending can all reduce it, in any year.
- The fixed amount is **not** recomputed from the remaining balance. It is 5%,
  10% or 20% of the starting balance, every year.
- The three percentages are a limited menu, not a finding. They came from the
  earlier search's habit of spreading a quarter, a half or all of the IRA over
  five years — 25%, 50% or 100% of the balance ÷ 5, the old `level_25/50/100`
  labels — and they were kept because a benchmark showed that, with these three, the simple
  strategies match what the retired search found. An amount between them is
  not tried.
- A custom amount or duration (say, $75,000 a year for four years) is not
  offered. Use the What-if page's **Strategy** option to force one of the
  named strategies.

The Review step of the wizard lists exactly this menu, with the dollar amounts
for your balance.

---

## Stop-year variants

Each of the eight converting strategies is first built in full: the rule is
applied every year of the plan, on the steady-return projection, and the
amount it produces each year is recorded. That gives one schedule per rule.

Then, for every year the rule converted in, the search adds a variant that
stops after that year. The variants are prefixes of the full schedule — the
same amounts up to the stop year, zero after it — so nothing is recomputed:

| Variant | Year 1 | Year 2 | Year 3 | Year 4 | Later years |
|---|---:|---:|---:|---:|---|
| Stop after year 1 | $50,000 | $0 | $0 | $0 | $0 |
| Stop after year 2 | $50,000 | $50,000 | $0 | $0 | $0 |
| Stop after year 3 | $50,000 | $50,000 | $50,000 | $0 | $0 |
| Every year (the full rule) | $50,000 | $50,000 | $50,000 | $50,000 | wherever the rule allows |

Each row is a separate strategy. Each is simulated through the last year of the
plan: stopping conversions does not stop withdrawals, Social Security, RMDs,
growth or taxes.

The rule's amount in a year depends only on the household's state that year,
and that state depends only on the conversions before it, so the prefix of
the full walk is exactly what "apply the rule through year N" would convert.
That is why a rule is walked once and its variants cost one simulation each.

How many strategies result is a property of your inputs, not a fixed number.
The ceiling is one variant per converting year per rule — on a 30-year plan,
at most 8 × 30 + 1 = 241 — but the real count is far lower, because most rules
stop converting on their own long before the plan ends (the IRA is used up,
RMDs or Social Security fill the bracket, or the money runs out), and because
two strategies with the same schedule are kept once. The four examples below
produce 97, 43, 112 and 76 strategies.

---

## What makes a strategy shrink or disappear

Building the schedules is where most of the "why is this strategy not here"
questions are answered. In order of how often they occur:

| Situation in a year | What the search does |
|---|---|
| The requested amount is more than the IRA holds, or more than your yearly cap allows | Converts the smaller amount. |
| The conversion would leave the year short of spending money | Converts only what the year can spare, which may be nothing. Spending is funded from the accounts as they stand at the start of the year, so converted dollars cannot pay for the same year's spending. |
| The year's income already fills the bracket, the conversion window is closed, or the Medicare or bracket setting forbids it | Converts $0 that year. The rule tries again next year. |
| The rule converts $0 in **every** year | Not kept — it would be *no conversions* under another name. |
| Spending cannot be funded in the **first** year, even converting nothing | The rule is dropped. (The *no conversions* baseline is kept and scored with its shortfalls.) |
| Spending cannot be funded in a **later** year | The walk stops building conversions at that year. The strategy is kept and simulated to the end of the plan, and every year it leaves unfunded counts against it. |

The last row matters most: a strategy that runs the money out is **not**
removed. It is scored with its shortfalls, which is what lets the optimizer
prefer a strategy that leaves money for later years.

---

## The steps at fixed claim ages

When every Social Security claim age is fixed, the strategy search is the
whole run. (When an age is searched, the same steps run inside a larger loop —
see [When claim ages are searched too](#when-claim-ages-are-searched-too).)

```
your inputs
     │
     ▼
1. build the eight rule schedules         one steady-return walk per rule
     │
     ▼
2. add the stop-year variants             prefixes of each walk
     │
     ▼
3. remove duplicates; add no conversions  the full list of strategies
     │
     ▼
4. rank on the steady-return value        informational at fixed ages
     │
     ▼
5. stage 1: EVERY strategy on the         the first third of the budget
   first 100 market scenarios             (100 of 300)
     │
     ▼
6. stage 2: the top 3 from stage 1,       the same 100 scenarios plus the
   plus no conversions, on all 300        remaining 200
     │
     ▼
7. rank the fully scored strategies       modeled score; success probability
   by modeled score                       only to break a tie
     │
     ▼
8. compare the winner with each           paired, scenario by scenario, with
   other finalist                         the four labels
     │
     ▼
recommendation + year-by-year plan        from the winner's steady-return run
```

What to know about each step:

1. **Build.** Each rule is walked once on the steady-return projection, year
   by year, with the full tax engine: the year is solved, the amount the rule
   produces is recorded, and the state moves on.
2. **Variants.** One per converting year, as above.
3. **Duplicates.** Two strategies whose schedules are identical (ignoring
   trailing zeros) are kept once, under the name registered first — the full
   rule's name wins over a variant's.
4. **Steady-return ranking.** Every strategy already has a steady-return
   value from being built. At fixed claim ages this ranking decides nothing:
   every strategy goes on to stage 1 regardless. It is shown on the Results
   page's steady-return comparisons, and it is the screen the claim-age
   search uses.
5. **Stage 1.** Every strategy is simulated on the first 100 market
   scenarios (one third of the 300-scenario budget). They share the
   scenarios, so the ranking is a fair paired comparison even on a small
   sample.
6. **Stage 2.** The three best stage-1 averages are extended to all 300
   scenarios by adding the other 200 — the first 100 are not redrawn. *No
   conversions* is always extended too, whatever its stage-1 rank, so "do
   nothing" is judged on the same evidence as the strategies that would
   replace it. A strategy you force from the What-if page is extended as
   well, so its figures rest on the full count, but it keeps its stage-1
   rank.
7. **Ranking.** Only fully scored strategies are ranked. A strategy
   eliminated in stage 1 cannot win at any budget: it lost on the evidence
   available, and a noisier estimate is not grounds to bring it back. Among
   the finalists the order is by modeled score; the share of scenarios that
   funded spending breaks a tie and does nothing else. Shortfalls lower the
   score as penalties; the optimizer does not rank funded strategies above
   underfunded ones as a rule.
8. **Comparison.** The winner is compared with each other finalist scenario
   by scenario, giving the average difference and a 95% interval. The
   labels are *Recommendation ahead*, *Alternative ahead*, *Practically
   equivalent* (the interval fits inside the comparison threshold, the larger
   of $5,000 and 0.25% of investable assets) and *Too close to distinguish*.

The Results page's *Close alternatives* table is step 8; its *Explore other
Social Security claim ages* section is the claim-age search's own screen.

---

## Example 1 — a comfortably funded couple

The standard test household used throughout the project's documentation,
given Social Security. Both 62, married filing jointly in California, with
$400,000 in a taxable account (basis $300,000), $2,500,000 traditional,
$50,000 Roth, a $30,000 pension, $90,000 of after-tax spending, planning 30
years from 2026; Social Security of $2,800 and $1,600 a month at full
retirement age, claimed at 67.

#### 1. Building the strategies

| Rule | Amount asked each year | Result | Years that convert | Converting years | Total converted | First shortfall (steady return) | Stop-year variants kept |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Fill the 10% bracket every year | — | kept | 12 | 2026–2037 | $210,331 | — | 11 |
| Fill the 12% bracket every year | — | kept | 13 | 2026–2038 | $983,746 | — | 12 |
| Fill the 22% bracket every year | — | kept | 16 | 2026–2041 | $2,757,621 | — | 15 |
| Fill the 24% bracket every year | — | kept | 7 | 2026–2032 | $2,220,710 | — | 6 |
| Fill the 32% bracket every year | — | kept | 6 | 2026–2031 | $2,001,960 | — | 5 |
| Convert up to $125,000 annually | $125,000 | kept | 28 | 2026–2053 | $3,500,000 | — | 27 |
| Convert up to $250,000 annually | $250,000 | kept | 10 | 2026–2035 | $2,273,190 | — | 9 |
| Convert up to $500,000 annually | $500,000 | kept | 4 | 2026–2029 | $2,000,000 | — | 3 |

**97 strategies** in all, including *no conversions*.

#### 2. Steady-return ranking (top 8 and no conversions)

| # | Strategy | Years converting | Total converted | Steady-return value | Unfunded spending (PV) |
|---:|:---|---:|---:|---:|---:|
| 1 | Fill the 12% bracket every year | 13 | $983,746 | $5,764,596 | $0 |
| 2 | Fill the 12% bracket through 2037 | 12 | $925,683 | $5,751,849 | $0 |
| 3 | Fill the 12% bracket through 2036 | 11 | $869,376 | $5,738,819 | $0 |
| 4 | Fill the 12% bracket through 2035 | 10 | $814,692 | $5,725,450 | $0 |
| 5 | Convert up to $125,000 annually through 2037 | 12 | $1,500,000 | $5,716,497 | $0 |
| 6 | Convert up to $125,000 annually through 2036 | 11 | $1,375,000 | $5,713,990 | $0 |
| 7 | Convert up to $125,000 annually through 2038 | 13 | $1,625,000 | $5,711,768 | $0 |
| 8 | Fill the 12% bracket through 2034 | 9 | $761,567 | $5,711,749 | $0 |
| 77 | No conversions | 0 | $0 | $5,439,710 | $0 |

#### 3. Stage 1 — every strategy on the first 100 market scenarios (top 8 and no conversions)

| # | Strategy | Steady-return rank | Average score, 100 scenarios | Carried to all scenarios |
|---:|:---|---:|---:|:---|
| 1 | Fill the 12% bracket every year | 1 | $5,973,540 | yes |
| 2 | Fill the 12% bracket through 2037 | 2 | $5,961,674 | yes |
| 3 | Fill the 12% bracket through 2036 | 3 | $5,949,087 | yes |
| 4 | Fill the 12% bracket through 2035 | 4 | $5,935,480 |  |
| 5 | Fill the 12% bracket through 2034 | 8 | $5,921,812 |  |
| 6 | Convert up to $125,000 annually through 2038 | 7 | $5,916,600 |  |
| 7 | Convert up to $125,000 annually through 2037 | 5 | $5,913,590 |  |
| 8 | Convert up to $125,000 annually through 2039 | 10 | $5,912,948 |  |
| 80 | No conversions | 77 | $5,646,947 | yes |

#### 4. Finalists on all 300 market scenarios

| Strategy | Modeled score | Spending funded | Compared with the winner | Alternative minus winner | 95% interval |
|:---|---:|---:|:---|---:|---:|
| Fill the 12% bracket every year | $5,816,505 | 100.0% | winner | — | — |
| Fill the 12% bracket through 2037 | $5,804,753 | 100.0% | Recommendation ahead | −$11,752 | [−$12,882, −$10,623] |
| Fill the 12% bracket through 2036 | $5,792,438 | 100.0% | Recommendation ahead | −$24,066 | [−$26,318, −$21,815] |
| No conversions | $5,498,744 | 100.0% | Recommendation ahead | −$317,761 | [−$349,072, −$286,449] |

Comparison threshold (materiality): $7,375.

**Recommendation: Fill the 12% bracket every year** — converts $103,000 in 2026, $983,746 over 13 years, last conversion 2038; spending funded in 100.0% of scenarios.

**What to notice**

- **Every rule produced a schedule and none was cut short.** The plan never runs short of spending money, so the *First shortfall* column is empty and no strategy carries a shortfall.
- **97 strategies from 8 rules**, far below the 241 ceiling. The *Convert up to $125,000* rule converts for 28 years and brings 27 stop-year variants; *Convert up to $500,000* empties the IRA in 4 years and brings 3.
- **A bracket fill is not a fixed amount.** *Fill the 12% bracket* converts $103,000 in 2026 and about $107,000–$123,000 a year through 2030, then $48,000–$58,000 a year from 2031. The drop is Social Security starting at 67: the benefit takes bracket room, and the conversion is what the bracket leaves.
- **Steady-return rank and stage-1 rank agree at the top but not everywhere.** The *$125,000 through 2037* variant is 5th on the steady-return projection and 7th on the first 100 scenarios. At fixed claim ages the disagreement costs nothing, because every strategy was simulated in stage 1 regardless.
- **Stage 2 is the top 3 plus *no conversions*.** *No conversions* was 80th of 97 in stage 1 and is still scored on all 300 scenarios, so the $317,761 gap to the winner rests on the same evidence as the other comparisons.
- **The averages move with the budget; the order does not.** The leader's average was $5,973,540 on the first 100 scenarios and $5,816,505 on all 300 — the first hundred happened to be kinder markets. The three finalists kept their order, and every interval excludes zero: each row reads *Recommendation ahead*. All four finalists fund spending in every scenario, so the score alone decides.

---

## Example 2 — a small IRA and a tight budget

Ages 65 and 63, married filing jointly in California, $500,000 traditional
and nothing else, $60,000 of after-tax spending for 30 years from 2026;
Social Security of $2,000 and $1,200 a month at full retirement age, claimed
at 67. Until the benefits start in 2028 every dollar of spending comes from
the IRA.

#### 1. Building the strategies

| Rule | Amount asked each year | Result | Years that convert | Converting years | Total converted | First shortfall (steady return) | Stop-year variants kept |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Fill the 10% bracket every year | — | kept | 14 | 2026–2039 | $203,866 | 2048 | 13 |
| Fill the 12% bracket every year | — | kept | 4 | 2026–2029 | $332,797 | 2046 | 3 |
| Fill the 22% bracket every year | — | kept | 3 | 2026–2028 | $292,356 | 2042 | 2 |
| Fill the 24% bracket every year | — | kept | 2 | 2026–2027 | $329,460 | 2041 | 1 |
| Fill the 32% bracket every year | — | kept | 1 | 2026–2026 | $299,850 | 2039 | 0 |
| Convert up to $25,000 annually | $25,000 | kept | 9 | 2026–2034 | $225,000 | 2047 | 8 |
| Convert up to $50,000 annually | $50,000 | kept | 6 | 2026–2031 | $275,935 | 2046 | 5 |
| Convert up to $100,000 annually | $100,000 | kept | 3 | 2026–2028 | $300,000 | 2044 | 2 |

**43 strategies** in all, including *no conversions*.

*No conversions* first runs short in 2050 on the steady-return projection. These are steady-return dates; each market scenario has its own.

#### 2. Steady-return ranking (top 8 and no conversions)

| # | Strategy | Years converting | Total converted | Steady-return value | Unfunded spending (PV) |
|---:|:---|---:|---:|---:|---:|
| 1 | No conversions | 0 | $0 | −$153,135 | $153,135 |
| 2 | Fill the 10% bracket through 2026 | 1 | $1,340 | −$153,595 | $153,595 |
| 3 | Fill the 10% bracket through 2027 | 2 | $2,462 | −$153,958 | $153,958 |
| 4 | Fill the 10% bracket through 2028 | 3 | $15,353 | −$159,344 | $159,344 |
| 5 | Fill the 10% bracket through 2029 | 4 | $19,412 | −$160,706 | $160,706 |
| 6 | Convert up to $25,000 annually through 2026 | 1 | $25,000 | −$162,805 | $162,805 |
| 7 | Fill the 10% bracket through 2030 | 5 | $35,651 | −$165,859 | $165,859 |
| 8 | Fill the 10% bracket through 2031 | 6 | $51,875 | −$170,815 | $170,815 |

#### 3. Stage 1 — every strategy on the first 100 market scenarios (top 8 and no conversions)

| # | Strategy | Steady-return rank | Average score, 100 scenarios | Carried to all scenarios |
|---:|:---|---:|---:|:---|
| 1 | Fill the 10% bracket through 2027 | 3 | −$127,803 | yes |
| 2 | Fill the 10% bracket through 2026 | 2 | −$127,812 | yes |
| 3 | No conversions | 1 | −$127,876 | yes |
| 4 | Fill the 10% bracket through 2028 | 4 | −$129,851 |  |
| 5 | Convert up to $25,000 annually through 2026 | 6 | −$130,479 |  |
| 6 | Fill the 10% bracket through 2029 | 5 | −$130,834 |  |
| 7 | Fill the 10% bracket through 2030 | 7 | −$132,928 |  |
| 8 | Convert up to $25,000 annually through 2027 | 9 | −$134,879 |  |

#### 4. Finalists on all 300 market scenarios

| Strategy | Modeled score | Spending funded | Compared with the winner | Alternative minus winner | 95% interval |
|:---|---:|---:|:---|---:|---:|
| Fill the 10% bracket through 2027 | −$142,418 | 23.7% | winner | — | — |
| Fill the 10% bracket through 2026 | −$142,422 | 23.7% | Practically equivalent | −$4 | [−$55, $47] |
| No conversions | −$142,462 | 23.7% | Practically equivalent | −$44 | [−$157, $69] |
| Fill the 32% bracket every year (pinned for contrast) | −$431,156 | 0.7% | Recommendation ahead | −$288,738 | [−$309,984, −$267,491] |

Comparison threshold (materiality): $5,000.

The last row is not part of a normal run: *Fill the 32% bracket* was 43rd of
43 after stage 1 and would have stayed at 100 scenarios. The script pins it
(`CONTRAST` in `walkthrough.py`), exactly as the What-if page pins a forced
strategy, so an eliminated strategy's full-budget score can be seen beside the
finalists. Pinning gives it the full budget; it does not change its rank.

**Recommendation: Fill the 10% bracket through 2027** — converts $1,340 in 2026, $2,462 over 2 years, last conversion 2027; spending funded in 23.7% of scenarios.

**What to notice**

- **The money runs short under every strategy on the steady-return projection**, first in 2039 under *Fill the 32% bracket* (which converts $299,850 of the $500,000 in its first year) and last in 2050 under *no conversions*; the rules fall between 2039 and 2048. The walk stops building conversions at that year; the strategy is kept and scored with its unfunded spending, which is why every steady-return value is negative. Each market scenario has its own first-shortfall year.
- **A negative score means the penalty for unfunded spending exceeds the average amount left for heirs.** It does not mean every simulated future ends with empty accounts: the winner funds spending in every year in 23.7% of scenarios, and those scenarios end with money. The score averages the good and bad scenarios together.
- **A requested amount is a maximum.** *Convert up to $50,000* converts $50,000 for five years and then $25,935 in 2031: the IRA, after that year's spending, had no more to give. *Fill the 10% bracket* asks for very little ($1,340 in 2026) because the spending drawn from the IRA already fills most of that bracket.
- **The steady-return ranking puts *no conversions* first; the first 100 scenarios put two tiny 10%-bracket variants ahead of it** by $64 and $73. All three went to the full budget, and on 300 scenarios they are $4 and $44 apart against a $5,000 comparison threshold: both rows read *Practically equivalent*. The strategy named as the recommendation converts $2,462 in total. Small conversions and no conversions produced nearly identical results for this household.
- **Larger conversions performed worse.** The pinned *Fill the 32% bracket* funds spending in 0.7% of scenarios and trails the winner by $288,738, and the stage-1 ranking falls, with few exceptions, as total conversions rise. The leading strategies fund spending in about 24 of 100 simulated futures, so changing conversions alone did not resolve the spending gap. A household in this position needs a spending or claiming decision, and the What-if page is where to test those.

---

## Example 3 — a very large IRA and modest spending

Both 62, married filing jointly in California, $500,000 taxable (basis
$400,000), $6,000,000 traditional, $100,000 Roth, $80,000 of after-tax
spending for 30 years from 2026; Social Security of $3,500 and $2,000 a month
at full retirement age, claimed at 70.

#### 1. Building the strategies

| Rule | Amount asked each year | Result | Years that convert | Converting years | Total converted | First shortfall (steady return) | Stop-year variants kept |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Fill the 10% bracket every year | — | kept | 12 | 2026–2038 | $561,249 | — | 11 |
| Fill the 12% bracket every year | — | kept | 13 | 2026–2038 | $1,253,271 | — | 12 |
| Fill the 22% bracket every year | — | kept | 13 | 2026–2038 | $2,412,625 | — | 12 |
| Fill the 24% bracket every year | — | kept | 20 | 2026–2045 | $6,773,281 | — | 19 |
| Fill the 32% bracket every year | — | kept | 14 | 2026–2039 | $5,802,658 | — | 13 |
| Convert up to $300,000 annually | $300,000 | kept | 27 | 2026–2052 | $8,036,772 | — | 26 |
| Convert up to $600,000 annually | $600,000 | kept | 8 | 2026–2033 | $4,744,887 | — | 7 |
| Convert up to $1,200,000 annually | $1,200,000 | kept | 4 | 2026–2029 | $4,128,277 | — | 3 |

**112 strategies** in all, including *no conversions*.

#### 2. Steady-return ranking (top 8 and no conversions)

| # | Strategy | Years converting | Total converted | Steady-return value | Unfunded spending (PV) |
|---:|:---|---:|---:|---:|---:|
| 1 | Fill the 22% bracket every year | 13 | $2,412,625 | $14,133,413 | $0 |
| 2 | Fill the 22% bracket through 2037 | 12 | $2,222,205 | $14,101,779 | $0 |
| 3 | Fill the 12% bracket every year | 13 | $1,253,271 | $14,092,729 | $0 |
| 4 | Fill the 22% bracket through 2036 | 11 | $2,037,464 | $14,073,281 | $0 |
| 5 | Fill the 12% bracket through 2037 | 12 | $1,173,260 | $14,070,553 | $0 |
| 6 | Fill the 12% bracket through 2036 | 11 | $1,095,140 | $14,042,693 | $0 |
| 7 | Fill the 22% bracket through 2035 | 10 | $1,858,146 | $14,042,143 | $0 |
| 8 | Fill the 12% bracket through 2035 | 10 | $1,018,811 | $14,019,826 | $0 |
| 100 | No conversions | 0 | $0 | $13,414,281 | $0 |

#### 3. Stage 1 — every strategy on the first 100 market scenarios (top 8 and no conversions)

| # | Strategy | Steady-return rank | Average score, 100 scenarios | Carried to all scenarios |
|---:|:---|---:|---:|:---|
| 1 | Fill the 22% bracket every year | 1 | $14,634,765 | yes |
| 2 | Fill the 22% bracket through 2037 | 2 | $14,603,596 | yes |
| 3 | Fill the 22% bracket through 2036 | 4 | $14,570,026 | yes |
| 4 | Fill the 22% bracket through 2035 | 7 | $14,533,233 |  |
| 5 | Fill the 12% bracket every year | 3 | $14,525,683 |  |
| 6 | Fill the 12% bracket through 2037 | 5 | $14,500,406 |  |
| 7 | Fill the 22% bracket through 2034 | 9 | $14,494,532 |  |
| 8 | Fill the 12% bracket through 2036 | 6 | $14,473,129 |  |
| 102 | No conversions | 100 | $13,789,549 | yes |

#### 4. Finalists on all 300 market scenarios

| Strategy | Modeled score | Spending funded | Compared with the winner | Alternative minus winner | 95% interval |
|:---|---:|---:|:---|---:|---:|
| Fill the 22% bracket every year | $14,321,468 | 100.0% | winner | — | — |
| Fill the 22% bracket through 2037 | $14,291,348 | 100.0% | Recommendation ahead | −$30,120 | [−$33,246, −$26,994] |
| Fill the 22% bracket through 2036 | $14,258,684 | 100.0% | Recommendation ahead | −$62,785 | [−$69,030, −$56,540] |
| No conversions | $13,504,088 | 100.0% | Recommendation ahead | −$817,381 | [−$897,209, −$737,552] |

Comparison threshold (materiality): $16,500.

**Recommendation: Fill the 22% bracket every year** — converts $243,600 in 2026, $2,412,625 over 13 years, last conversion 2038; spending funded in 100.0% of scenarios.

**What to notice**

- **112 strategies, the most of the four examples**, because the heavy rules keep converting for a long time: *Convert up to $300,000* for 27 years (26 variants), *Fill the 24% bracket* for 20 (19 variants).
- **A rule can convert more than the starting balance.** *Fill the 24% bracket* converts $6,773,281 over 20 years from a $6,000,000 IRA, because the IRA keeps growing while it is being drained. *Convert up to $1,200,000* empties it in 4 years.
- ***No conversions* is 100th of 112 on the steady-return projection and 102nd in stage 1.** With RMDs on $6,000,000 ahead, almost any conversion beats doing nothing; the gap to the winner is $817,381.
- **Here the stage-1 cut matters.** *Fill the 12% bracket every year* was 3rd on the steady-return projection but 5th on the first 100 scenarios, so it was not carried to the full budget; only the 22%-bracket family was. A strategy cut in stage 1 cannot win at any budget — this is the price of screening, and the exports show each strategy's scenario count so the cut is visible.
- **The comparison threshold scales with assets**: $16,500 here (0.25% of $6.6 million), against $5,000 for the smaller households. The stop-2037 variant trails by $30,120 with an interval that excludes zero, so the full rule is *Recommendation ahead* of its closest alternative.

---

## Example 4 — still working

Ages 58 and 56, married filing jointly in California, salaries of $150,000
(through 2031) and $60,000 (through 2029), $200,000 taxable (basis $150,000),
$1,000,000 traditional, no Roth, $110,000 of after-tax spending for 35 years
from 2026; Social Security of $3,200 and $1,500 a month at full retirement
age, claimed at 67.

#### 1. Building the strategies

| Rule | Amount asked each year | Result | Years that convert | Converting years | Total converted | First shortfall (steady return) | Stop-year variants kept |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Fill the 10% bracket every year | — | kept | 5 | 2032–2036 | $287,471 | — | 4 |
| Fill the 12% bracket every year | — | kept | 15 | 2031–2045 | $1,068,083 | — | 14 |
| Fill the 22% bracket every year | — | kept | 10 | 2026–2035 | $1,197,620 | — | 9 |
| Fill the 24% bracket every year | — | kept | 5 | 2026–2030 | $1,110,461 | — | 4 |
| Fill the 32% bracket every year | — | kept | 4 | 2026–2029 | $1,054,289 | — | 3 |
| Convert up to $50,000 annually | $50,000 | kept | 19 | 2026–2044 | $950,000 | — | 18 |
| Convert up to $100,000 annually | $100,000 | kept | 11 | 2026–2036 | $1,100,000 | — | 10 |
| Convert up to $200,000 annually | $200,000 | kept | 6 | 2026–2031 | $1,143,162 | — | 5 |

**76 strategies** in all, including *no conversions*.

#### 2. Steady-return ranking (top 8 and no conversions)

| # | Strategy | Years converting | Total converted | Steady-return value | Unfunded spending (PV) |
|---:|:---|---:|---:|---:|---:|
| 1 | Fill the 10% bracket every year | 5 | $287,471 | $827,605 | $0 |
| 2 | Fill the 10% bracket through 2035 | 4 | $250,362 | $815,849 | $0 |
| 3 | Fill the 10% bracket through 2034 | 3 | $214,300 | $803,643 | $0 |
| 4 | Fill the 10% bracket through 2033 | 2 | $140,100 | $771,915 | $0 |
| 5 | Fill the 12% bracket through 2033 | 3 | $328,450 | $756,221 | $0 |
| 6 | Fill the 10% bracket through 2032 | 1 | $68,000 | $738,275 | $0 |
| 7 | Fill the 12% bracket through 2032 | 2 | $162,900 | $735,442 | $0 |
| 8 | Fill the 12% bracket through 2034 | 4 | $498,925 | $734,136 | $0 |
| 21 | No conversions | 0 | $0 | $706,495 | $0 |

#### 3. Stage 1 — every strategy on the first 100 market scenarios (top 8 and no conversions)

| # | Strategy | Steady-return rank | Average score, 100 scenarios | Carried to all scenarios |
|---:|:---|---:|---:|:---|
| 1 | Fill the 10% bracket every year | 1 | $872,775 | yes |
| 2 | Fill the 10% bracket through 2035 | 2 | $868,424 | yes |
| 3 | Fill the 10% bracket through 2034 | 3 | $860,541 | yes |
| 4 | Fill the 10% bracket through 2033 | 4 | $833,212 |  |
| 5 | Fill the 12% bracket through 2033 | 5 | $812,835 |  |
| 6 | Fill the 12% bracket through 2034 | 8 | $807,397 |  |
| 7 | Fill the 10% bracket through 2032 | 6 | $804,194 |  |
| 8 | Fill the 12% bracket through 2032 | 7 | $798,923 |  |
| 21 | No conversions | 21 | $773,881 | yes |

#### 4. Finalists on all 300 market scenarios

| Strategy | Modeled score | Spending funded | Compared with the winner | Alternative minus winner | 95% interval |
|:---|---:|---:|:---|---:|---:|
| Fill the 10% bracket every year | $810,059 | 57.7% | winner | — | — |
| Fill the 10% bracket through 2035 | $805,365 | 58.0% | Recommendation ahead | −$4,694 | [−$5,952, −$3,437] |
| Fill the 10% bracket through 2034 | $797,945 | 58.0% | Recommendation ahead | −$12,114 | [−$14,534, −$9,694] |
| No conversions | $717,765 | 56.3% | Recommendation ahead | −$92,294 | [−$103,778, −$80,810] |

Comparison threshold (materiality): $5,000.

**Recommendation: Fill the 10% bracket every year** — converts $0 in 2026, $287,471 over 5 years, last conversion 2036; spending funded in 57.7% of scenarios.

**What to notice**

- **The low-bracket fills wait for the salaries to end.** With $210,000 of salary filling the 10% and 12% brackets, *Fill the 10% bracket* converts nothing until 2032, the first year with no salary. *Fill the 12% bracket* converts a token $4,150 in 2031 — the last salary year, when the inflation-indexed bracket just outgrows the one remaining $150,000 salary — and $158,750 in 2032. The 22%, 24% and 32% fills convert from 2026, because the salaries leave room in those brackets.
- **So nothing is dropped for a working household; the schedules start late.** The recommendation, *Fill the 10% bracket every year*, converts **$0 in 2026**. That zero is the decision for this year, not a missing strategy, and the Results page says so.
- **76 strategies; *no conversions* ranks 21st on both rankings.** The 55 strategies below it all convert during the salary years, at 22% and above.
- **Spending is funded in about 58% of scenarios for every finalist.** $110,000 a year for 35 years is more than these assets and benefits carry in many markets, and every finalist is in the same position (56.3%–58.0%), so the score, not the funded share, separates them: the winner leads *no conversions* by $92,294.
- **A lead smaller than the threshold can still be decisive.** The winner's average lead over the stop-2035 variant is $4,694, less than the $5,000 threshold, yet the row reads *Recommendation ahead*: *Practically equivalent* requires the whole 95% interval to fit inside the threshold, and this one ([−$5,952, −$3,437]) excludes zero and reaches past it.

---

## When claim ages are searched too

With at least one Social Security age searched, the strategy search above
runs once for **every eligible combination of claim ages**, and the
recommendation is a claim-age pair and a strategy together. What changes:

| | Fixed claim ages | Searched claim ages |
|---|---|---|
| Strategies built | Once | Once per eligible claim-age pair — every whole age from 62 (or the current age) to 70 for each searched person, minus the exclusions below |
| Into stage 1 | Every strategy | Per pair, the 3 best by steady-return value plus *no conversions*. At the pair you entered for comparison, **every** strategy |
| Stage 1 budget | 100 scenarios | 50 scenarios (the first 50 of the 300) |
| Into stage 2 | Top 3 by stage-1 average, plus *no conversions* | Top 5 by stage-1 average across all pairs, plus every strategy at your comparison pair |
| Always fully scored | *No conversions* | *No conversions* at the winning pair (and at your comparison pair) |
| Winner | Best fully scored strategy | Best fully scored strategy at an eligible pair |
| Afterwards | — | Lifespan checks: the top 3 re-scored with the plan ending 5 years earlier and later and, for a couple, with either spouse dying at 78 |

Here the steady-return ranking **does** decide something: a strategy outside
a pair's top 3 by steady-return value is never simulated at that pair (unless
it is your comparison pair). The benchmark `backend/benchmarks/joint_screening.py`
measures what that screen leaves out; on the cases measured it left out
nothing of material size.

Excluded claim ages are reported with their reason beside the choice. One
exclusion is a modeling restriction rather than a finding: ages that overlap
salary income before full retirement age are skipped because the app does not
calculate Social Security's earnings test. It does not necessarily mean
benefits would not be payable at those ages.

Example 1 run again with both ages searched and 65/63 entered as the ages to
compare against:

81 claim-age pairs enumerated, 81 eligible; 0 exclusions. 420 candidates entered stage 1 (3 best by steady-return value plus no conversions per pair; every strategy at the entered pair) on 50 market scenarios; 5 finalists on all 300.

#### Finalists

| Claim ages | Strategy | Modeled score | Spending funded | Scenarios | Compared with the winner |
|:---|:---|---:|---:|---:|:---|
| 70/70 | Fill the 12% bracket every year | $5,898,802 | 100.0% | 300 | winner |
| 70/69 | Fill the 12% bracket every year | $5,894,935 | 100.0% | 300 | Practically equivalent |
| 69/70 | Fill the 12% bracket every year | $5,891,816 | 100.0% | 300 | Recommendation ahead |
| 69/69 | Fill the 12% bracket every year | $5,886,959 | 100.0% | 300 | Recommendation ahead |
| 70/68 | Fill the 12% bracket every year | $5,885,342 | 100.0% | 300 | Recommendation ahead |

**Winner: ages 70/70, Fill the 12% bracket every year**, score $5,898,802, spending funded 100.0%.

#### Baselines

| Baseline | Claim ages | Strategy | Modeled score | Spending funded | Scenarios |
|:---|:---|:---|---:|---:|---:|
| Your ages, best conversions | 65/63 | Fill the 12% bracket every year | $5,710,417 | 100.0% | 300 |
| Your ages, no conversions | 65/63 | No conversions | $5,405,983 | 100.0% | 300 |
| Winner's ages, no conversions | 70/70 | No conversions | $5,578,176 | 100.0% | 300 |

**What to notice**

- **81 claim-age pairs**, every age from 62 to 70 for each spouse, all eligible: nobody is receiving, over 70 or earning a salary. The strategy search ran 81 times, once per pair.
- **420 candidates entered stage 1, not 81 × 97.** At 80 of the pairs only the 3 best strategies by steady-return value plus *no conversions* were simulated; at the entered pair, 65/63, every strategy was, because that pair is reported in full as *Your ages*.
- **Stage 1 used 50 scenarios, and the 5 finalists were all the same strategy at neighbouring ages**: *Fill the 12% bracket every year* at 70/70, 70/69, 69/70, 69/69 and 70/68. The finalist cut-off fell at 69/68, which trailed 70/68 by about $2,700 on the first 50 scenarios and so was never scored on all 300.
- **The winner is 70/70, and the margins are what the labels say they are.** 70/69 trails by $3,867, inside the $7,375 threshold: *Practically equivalent*. 69/70 trails by $6,986 with an interval that excludes zero: *Recommendation ahead*, by a little. Claiming at 70 wins here because the couple is funded from the IRA until then, which keeps the brackets open for conversions for three more years.
- **The baselines are what the Results page compares against.** Your ages with their best conversions (65/63, the same 12%-bracket rule) score $188,385 less than the winner; your ages without conversions, $492,819 less; the winner's ages without conversions, $320,627 less. Each baseline was scored on all 300 scenarios, however it ranked in stage 1.
- **The whole search took about six minutes** against about a minute for the fixed-age run of the same household — the cost of the 81 strategy searches and the 420 stage-1 candidates.

---

## What the search cannot find

The optimizer finds the best strategy **among the ones it builds**, judged on
the evidence it gathers. It is not a proof that no other schedule would do
better:

- **An amount between the menu's steps.** Converting $75,000 a year when the
  menu offers $50,000 and $100,000, or filling to a point inside a bracket.
- **A later start chosen for its own sake.** A strategy converts in every
  year its rule allows from the first year on. A delayed start arises only
  when the rule finds no room early (a salary, as in Example 4) or from the
  conversion window setting (before Medicare, before RMDs, before Social
  Security), which applies to every strategy alike.
- **A strategy cut in stage 1.** Three survivors plus *no conversions* go to
  the full budget; a strategy that trailed on the first 100 scenarios is not
  reconsidered.
- **In a claim-age search, a strategy outside a pair's top 3 by steady-return
  value.** The deterministic screen is what makes searching dozens of pairs
  affordable.
- **Anything the model does not represent.** See the User Guide's
  [Assumptions and limits](USER_GUIDE.md#9-assumptions-and-limits).

What the search does guarantee: every strategy it compares is simulated over
your whole plan with the full tax engine, on the same market scenarios, and
nothing is ranked above *no conversions* without being measured on the same
evidence.

---

## Reproducing these tables

```
cd backend && uv run python -m benchmarks.walkthrough --out /tmp/walkthrough.json
cd backend && uv run python -m benchmarks.walkthrough --case tight
```

The script defines the four households in code, runs the same `search` and
staged scoring the app runs (seed 42, 300 scenarios, the first 100 as stage
1), and prints every table above; `--out` also writes every number as JSON.
The `happy` household is run a second time as a claim-age search with
`--case joint`. Each fixed-age case takes under a minute on a laptop; the
claim-age search takes several minutes.
