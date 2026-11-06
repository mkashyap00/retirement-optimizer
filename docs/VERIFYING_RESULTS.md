# Verifying the results

A companion to the [User Guide](USER_GUIDE.md) for readers who want to check
the app's numbers: the identities every run satisfies, the Excel **Tax Audit**
sheet, and how to tie a run out against an independent model or your own
spreadsheet. For how strategies are built and ranked, see
[Optimizer internals](OPTIMIZER_INTERNALS.md).

## Built-in identities

- **Spending is funded after tax.** Each year the engine solves withdrawals so
  that net cash after federal tax, state tax and Medicare surcharges equals the
  year's spending target to within $1. In any exported row, to within $1:
  `cash income + RMD + spending withdrawals − total tax = required spending + surplus saved − shortfall`.
  Cash income is salary, pension, rental income, the whole Social Security
  benefit, interest and dividends; spending withdrawals are the taxable,
  traditional and Roth withdrawals that fund the year. Roth conversions are not
  spending withdrawals — they move money between accounts and show up only
  through their tax. A funded year without a surplus has neither of the last
  two terms.
- **A conversion never takes money the year needs.** If a conversion would
  leave the year short of spending, it is cut back to what the year can spare,
  in the steady-return projection and in every market scenario.
- **Property-based tests.** The project's tests check its promises on hundreds
  of randomly generated households: a *fill NN%* conversion never lands above
  that bracket, nothing a bracket cap allows lands above it, every year funds
  its spending unless the accounts are empty, and RMDs start at the right age
  for the birth year.
- **Cited tax data.** Every bracket, deduction and Medicare threshold lives in a
  data file under `backend/src/data/tax_rules/`, each block citing its IRS
  Revenue Procedure or CMS notice, so any figure can be compared with its
  primary source without reading code.

## The Tax Audit sheet

The Excel export's **Tax Audit** sheet has one column per year and one row per
worksheet line:

- the ordinary-income stack: salary, pension, rental income, interest,
  ordinary dividends, traditional distributions (RMD, conversion and
  withdrawal), the net short-term capital gain, the capital loss deduction
  (shown negative), and gross and **taxable** Social Security;
- preferential income: qualified dividends and the net long-term capital gain;
- Schedule D: the short- and long-term gains already realized that you
  entered, the long-term gain from the plan's own sales, and the loss carried
  in and carried to the next year, by character;
- the federal derivation: the deduction and its type (the standard deduction
  includes the age-65 addition and the temporary senior deduction) → taxable
  income → tax on ordinary income, tax on gains and qualified dividends, net
  investment income tax → federal tax;
- state tax, the Medicare-surcharge income from two years earlier and the
  surcharge, and total tax.

The ordinary-income lines sum to the total shown, and federal + state + Medicare
surcharge equals the year's total tax. To verify a year by hand, take the lines
to the Form 1040 instructions — the *Qualified Dividends and Capital Gain Tax
Worksheet* and the *Social Security Benefits Worksheet* — or give the sheet to a
CPA. A quicker, weaker check: enter the same figures into a reputable 1040
calculator and expect agreement within rounding.

## Cross-checking the whole plan

For the multi-year trajectory, rebuild the household in an independent model —
the free Bogleheads *Retiree Portfolio Model* spreadsheet, or paid tools such as
Pralana or Boldin. Expect agreement in direction and magnitude, not to the
penny: planners differ in return sequencing and inflation treatment.
Differences to expect from this app's documented choices:

- tax tables past the latest published year are projected at your inflation
  assumption (federal brackets, deductions and Medicare thresholds; California's
  brackets), while other states stay at their latest values;
- Social Security grows by your COLA (your inflation rate unless set);
- the first two years' Medicare surcharges use an income estimate, because the
  income two years earlier is before the plan starts;
- the **spousal benefit** is applied — a spouse receives their own benefit plus
  the excess of 50% of the higher earner's PIA over their own (reduced if
  claimed before full retirement age), from the year the higher earner files —
  which hand-built spreadsheets often omit.

## Reconciling against your own spreadsheet

A personal conversion model can be tied out against this one closely. Most of
the work is making both answer the same question.

**Set the app up to match your sheet.**

1. **Tick *Skip market simulation*** on the What-if page. With the simulation
   on, the app ranks strategies on their average across the market scenarios minus
   the spending they fail to fund, so for an underfunded plan it can recommend
   no conversions where a sheet growing at a steady return shows a large one.
   That is a difference in what is being scored, not in tax.
2. **Force the same strategy on both sides** with **Strategy** under Advanced
   options — for example *Fill the 12% bracket every year* — so you compare
   schedules, not your schedule against the optimizer's pick.
3. **Clear Max ordinary-income bracket**, or apply the identical cap in your
   sheet. A low cap can forbid conversions entirely.
4. **Compare like with like.** The app maximizes the after-tax estate net of
   unfunded spending. A sheet that minimizes lifetime tax will favor plans with
   less income.

**Compare taxable ordinary income, not conversion dollars.** *Fill the 12%
bracket* means that after the conversion, taxable ordinary income sits at the
top of the 12% bracket. Two models can agree on that figure while converting
different amounts, because the conversion is the last item in the
ordinary-income stack: Social Security, a traditional withdrawal or an RMD
displaces conversion dollar for dollar. Read taxable ordinary income from the
Tax Audit sheet.

**Where the two usually differ, in the order you will meet them:**

| Symptom | Usual cause |
|---|---|
| The app converts nothing | The simulation was left on, or the bracket cap forbids it (steps 1 and 3). |
| Conversions differ from the year Social Security starts | Your sheet may omit the spousal benefit. Up to 85% of the difference is taxable ordinary income and displaces conversion one-for-one. |
| Conversions differ only in later years | The app solves withdrawals to fund your inflating spending target; a sheet usually takes withdrawals as typed. Once the taxable account is empty, the app draws from the traditional IRA, which is ordinary income and uses bracket room before any conversion. Compare the funded-spending line first. |
| Your sheet shows lower tax on the same income | Check it computes net investment income tax (3.8% above $250,000 joint MAGI, not indexed) and charges Medicare surcharges per person on Medicare, not per household. |
| Small differences that grow from the second year | Tax tables are projected here at your inflation assumption, and Social Security grows by your COLA. A sheet that freezes either drifts apart over time; set the COLA to 0 to match flat benefits. |

If a difference remains after all of these, it is worth reporting.
