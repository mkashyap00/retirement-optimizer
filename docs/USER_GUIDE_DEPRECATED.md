# User Guide (deprecated)

> **Superseded.** This is the previous user guide, kept for its history: the
> August and October 2026 rebuilds, retired settings and strategies, and the
> worked examples measured along the way. Some of it no longer describes the
> app. For current use, read the [User Guide](USER_GUIDE.md).

This guide explains every field in the planning wizard, how to read the results, and how to keep the tax data current each year.

**Intended cadence:** this is an *annual-planning* tool. Act on the current year's recommendation, then re-run each year with your real balances and the latest tax data — the projection beyond year one is a compass, not a schedule to execute blindly.

> **Made a plan before 16 October 2026? Re-run it.** A set of calculation corrections landed then — surplus cash is now saved, the age-65 standard deduction is applied, Social Security and RMDs are computed per person correctly, Medicare surcharges are always counted, and more. They can change the recommendation, not just the figures. See [The October 2026 corrections](#the-october-2026-corrections).

---

## Start here: what this tool optimizes

**The objective is to fund your spending and leave the largest after-tax estate.** Taxes count through the estate: every dollar of tax paid, this year or in thirty years, is a dollar the estate no longer holds. Everything the tool does serves that goal. (Until October 2026 an *Optimization Priority* setting let you score lifetime taxes separately from the estate; see [The objective](#the-objective) for why it was retired.)

If your goal is minimizing lifetime taxes, **three first-order decisions** dominate almost every retirement plan. Almost everything else is *second-order* — it changes the constraints or opportunities *within* these three, rather than being a decision of its own.

### 1. Annual spending — the size of the tax problem

*How much after-tax income do you need each year?* This is the biggest driver, because it sets how much you must withdraw. Raising spending from **$120,000 to $160,000** a year can push you into higher brackets, trigger larger Medicare **IRMAA** surcharges, pull more Social Security into taxation, shrink your Roth-conversion room, and inflate future RMDs. It determines the *size* of the tax problem.

> **In this tool:** spending is *your input* — the optimizer works within it, it does not choose it. To price what a different spending level would cost, change it on the **[What-if page](#the-what-if-page)** and compare the two runs side by side.

### 2. Withdrawal order — where the money comes from

*Which bucket do you spend from — taxable, Traditional, or Roth?* Same spending, very different tax bill. To raise **$150,000** you might take:

- **Option A:** $150k from the Traditional IRA → all ordinary income; or
- **Option B:** $60k dividends + $40k capital gains + $50k Roth → mostly preferential-rate or tax-free.

Order affects ordinary income, capital-gains rates, NIIT, Medicare premiums, future RMDs, and survivor taxes — it is one of the largest levers in retirement planning.

> **In this tool:** withdrawal order is a **two-position toggle**, not a search dimension. *Preserve Taxable Accounts* **off** = taxable → Traditional → Roth; **on** = Traditional → taxable → Roth (Roth is always drawn *last*, since it grows tax-free and is best for heirs). You choose it; the optimizer does not (yet) try both for you.

### 3. Roth conversions — pay tax now or later

*How much Traditional IRA do you voluntarily convert to Roth each year?* The most powerful long-term lever: deliberately realize income while your marginal rate is low, instead of letting RMDs force it out later at a higher rate. At age 60 with $40k of income, converting **$0 / $50k / $100k / $150k** each changes today's taxes, future RMDs, Medicare premiums, Social Security taxation, taxes after a spouse dies, and the heir-adjusted estate. In one phrase, it decides: **"pay tax now, or later?"**

> **In this tool:** this is the lever the optimizer always solves. Every strategy on the Results page — *Fill the 22% bracket every year*, *Fill the 12% bracket through 2031*, *Convert up to $100,000 annually*, *No conversions*, … — is a different year-by-year *conversion schedule*, and the recommendation is the schedule that best meets your objective. If converting doesn't help, it recommends **No conversions** (always a candidate, and always scored on the full set of market paths).

### Everything else is (mostly) a constraint

Other things matter too, but they mostly reshape the *constraints and opportunities* inside the three decisions above rather than being decisions of their own. Some of them the tool takes as **inputs**: your state of residence, your dividends and other income, and pensions. For example, a state with no income tax changes whether converting before or after a move pays off.

Others the tool **does not model at all**: qualified charitable distributions (QCDs), charitable giving, capital-gain and tax-loss harvesting, and asset allocation (every account earns the same expected return and volatility). If one of these is a big part of your plan, account for it outside the tool.

**Social Security claim age is the one exception you choose.** For each person
not already receiving benefits, you either hold the age you entered or let the
optimizer search every eligible age and choose it together with the conversion
schedule. The two interact: claiming later leaves more low-income years, which
are the cheap years to convert. See [Step 4 — Income and Social
Security](#step-4--income-and-social-security) for what the search does and
does not model.

### The mental model

> **Inputs (fixed):** account balances, tax law, expected return, life expectancy, Social Security & RMD rules — *plus your spending target and your withdrawal-order toggle.*
> **Decisions the optimizer controls:** the annual Roth-conversion amount, and — when you ask it to search — each person's Social Security claim age.
> **Objective:** maximize the present-valued, heir-adjusted estate, averaged across market scenarios, net of any spending a scenario fails to fund. Lifetime taxes are reported beside it, not scored separately.
> **Subject to:** funding your spending every year, plus your IRMAA policy, conversion window, and bracket limits.

**Why not optimize everything?** Of the three big knobs, the tool automates the one that is genuinely hard to reason about by hand (#3), and the claim age that interacts with it most, while giving you direct control of the other two — #1 as an input, #2 as a toggle. Letting the optimizer also *choose* the withdrawal order (and eventually explore spending levels) are natural future enhancements; today, those two are your dials.

---

## Table of Contents

1. [Start here: what this tool optimizes](#start-here-what-this-tool-optimizes)
2. [Key concepts (glossary)](#key-concepts-glossary)
3. [The Planning Wizard](#the-planning-wizard)
4. [Running the optimization](#running-the-optimization)
5. [Reading the Results](#reading-the-results)
6. [How the Optimizer Works](#how-the-optimizer-works)
7. [The What-if Page](#the-what-if-page)
8. [The Portfolio Sale Planner](#the-portfolio-sale-planner)
9. [Exports: CSV, Excel, and PDF](#exports-csv-excel-and-pdf)
10. [Verifying the numbers](#verifying-the-numbers)
11. [Your data stays on your machine](#your-data-stays-on-your-machine)
12. [AI Summary (optional)](#ai-summary-optional)
13. [Keeping tax data current](#keeping-tax-data-current)

---

## Key concepts (glossary)

A few terms recur throughout the app and this guide. Several describe **different scopes** — a plan, an optimization of that plan, and the strategy it recommends — and several say **what a number measures**, so it's worth getting them straight up front.

| Term | What it means |
|---|---|
| **Plan / household** | Everything you enter for one household: ages, accounts, income, and settings. Each plan is stored under its own **Household ID**. "Start a plan," "copy a plan," and "a household" all refer to this. The **portfolio is *not* part of a plan** — it lives one level up (see *Portfolio* below), so every plan shares the same uploaded holdings. |
| **Household ID** | The UUID that identifies a plan. Your accounts, settings, and runs are keyed to it. (The portfolio is **not** — it is app-level; see *Portfolio*.) It is shown on the Results page as "Plan (household) ID," beneath the Run ID, with the plan's nickname (as it was when the run was made) on the line below. |
| **Run** | One optimization of a plan. Every time you click the Review step's action (**Optimize conversions**, or **Optimize conversions and claim ages**), the app creates a *new* run — with its own **Run ID** — that points back at the household. Re-running the same plan produces a new Run ID each time; the plan itself is unchanged. |
| **Run ID** | The UUID under *Run details* beneath the heading on the Results page, and in every export/report URL (`/runs/<Run ID>/…`). This is what identifies a specific set of results. It is **not** the Household ID. |
| **Strategy (policy)** | One conversion schedule the optimizer scores, named after the rule that builds it: *Fill the 12% bracket every year*, *Fill the 12% bracket through 2031* (the same rule, stopping after 2031), *Convert up to $100,000 annually through 2029*, or *No conversions*. The **recommended strategy** is the one with the highest modeled score. Exports and older runs may show the internal id, such as `fill_12_annual`. See [The candidate strategies](#the-candidate-strategies). |
| **Claim-age search** | A run that tries every eligible Social Security claim age for at least one person, with a conversion strategy for each claim-age pair, and recommends the pair and strategy together. It runs in the background; see [Running the optimization](#running-the-optimization). |
| **Modeled score** | What the optimizer ranks on: the present value of the heir-adjusted estate, less a charge for any spending a plan fails to fund, averaged across the market scenarios. In today's dollars. It is not tax saved or extra estate; see [The objective](#the-objective). |
| **Steady-return projection** | A projection assuming every year earns exactly your assumed average return. The estate, lifetime taxes, charts and year-by-year table come from it. |
| **Market scenarios** | The 300 (by default) possible investment-return sequences each strategy is tested under; every strategy faces the same ones. The modeled score and the share of scenarios with spending funded come from them. See [Two kinds of number](#two-kinds-of-number). |
| **Comparison labels** | How a strategy compares with the recommendation, path by path: *Recommendation ahead*, *Alternative ahead*, *Practically equivalent* (similar enough to treat alike under the model's comparison threshold) or *Too close to distinguish* (not enough evidence to say which is better). See [Comparison labels](#comparison-labels). |
| **Portfolio** | The optional list of individual positions (tickers, shares, price, cost basis) — your actual holdings. It is **app-level**: uploaded once from the top-nav **Portfolio** tab and reused by every plan and run, so you refresh it episodically (monthly-ish), not per plan. It powers the Sale Planner (see below). Its positions do not otherwise drive the optimizer, with one convenience: when you start a plan, its total taxable cost basis **auto-fills the Accounts Cost Basis field** (which the tax projection *does* use). |
| **Sale Plan** | A point-in-time translation of one year's taxable withdrawal into a specific sell list, at today's prices. Shown inline on the results page (click *Plan this sale* on a year) and included in the run's CSV/Excel/PDF exports when a portfolio is uploaded. |
| **BETR** | Break-even tax rate for a conversion — a diagnostic, not the decision. See [How the Optimizer Works](#how-the-optimizer-works). |

**How they relate, by example.** You start a plan and name it "First" — that creates a *household* (Household ID). You fill in the wizard, let it search your claim ages, and click **Optimize conversions and claim ages** — that starts a *claim-age search*, and when it finishes it saves a *run* (Run ID). The results recommend claiming at 70 and 67 with *Fill the 12% bracket through 2031*. Later you upload your *portfolio* and generate a *Sale Plan* for the year you're about to act on. To see a different choice — say, claiming at 67 — change it on the What-if page, or copy the plan, change the input and run it again; either way the original run is untouched.

---

## The Planning Wizard

The wizard collects your household information across six steps: Household Profile, Planning Assumptions, Accounts, Income & Social Security, Spending and goals, and Review and run. Review and run asks nothing new: it summarizes your choices and starts the calculation. All fields have a help tooltip you can hover for more detail. A summary of what you have entered so far stays beside the form until the last step. Impossible values — a negative balance, a rate typed as a whole number, income that ends before it starts, a state code that isn't a US state — are refused with a message rather than saved.

### Starting a plan: fresh or copied

When prior plans exist, the wizard first asks whether to **start fresh** or **copy every input from a previous plan** — the copy flow is the fast way to run a what-if (change one input, keep the rest). Two behaviors worth knowing:

- The **Copy from** dropdown shows the **10 newest plans** (nickname + date). If a plan you want has aged out of the list, delete stale experiment plans from the dashboard (the trash icon, **Delete plan**, on the plan's card) to make room — the list is newest-first.
- Deleting a plan from the dashboard removes its accounts, income, settings and runs all at once; if anything fails part-way, nothing is deleted. Your uploaded portfolio is never touched.
- A copied plan's nickname is prefilled as **"Copy of &lt;name&gt;"**, so forgetting to rename it can never produce two plans with identical names. Copying never modifies the original plan.
- Saving a copied plan creates a **brand-new Household ID** — the original ("First") and the copy ("Second") are independent plans. Your **portfolio is unaffected**: it's app-level, not stored inside a plan, so both plans automatically share the one portfolio you uploaded. You never re-upload it when copying.

### Step 1 — Household Profile

| Field | What it means |
|-------|---------------|
| **Filing Status** | Single or Married Filing Jointly. This determines which tax brackets, standard deductions, and IRMAA thresholds apply. |
| **Your Birth Date** | Used to calculate your age — the age you reach this calendar year, which is the age the tax rules use — Required Minimum Distribution (RMD) start age, and Social Security benefit timing. The **birth year** sets the RMD start age under SECURE 2.0: **73** if you were born 1951–1959, **75** if born 1960 or later. |
| **Spouse Birth Date** | Only shown for joint filers. Both birth dates matter because RMDs and SS benefits are calculated per person. |
| **Plan through age** | Required, for each of you. The projection runs through the year the later of you reaches this age (at least 10 years). It is a planning assumption, not a prediction of lifespan; a new plan starts at **95**, a modeling default you can change. The Review step shows the year the projection ends. A plan saved before October 2026 with these left blank projected 30 years; copying it fills in the ages that give the same end year, so its assumptions do not change. |
| **State of Residence** | Determines your state income tax: its brackets and standard deduction, applied to your income as one total. States with no income tax, and the Social Security treatment below, are handled. **Exemptions for pension or IRA income are not**: the state engine cannot tell those apart from other ordinary income, so in a state that excludes some retirement income it overstates the tax. |

> **How the engine handles state Social Security taxation.**
> As of 2026, only **8 states** tax Social Security benefits: Colorado, Connecticut, Minnesota, Montana, New Mexico, Rhode Island, Utah, and Vermont. The remaining 42 states and D.C. fully exempt Social Security from state income tax — the engine excludes it automatically.
>
> For the 8 taxing states the engine uses a **binary approximation**: it includes 85% of your Social Security in state taxable income (matching the maximum federal inclusion rate), then applies the state's brackets and standard deduction. In reality, most of these states offer **income-based exemptions** that reduce or eliminate the state tax on Social Security for moderate-income retirees — for example, Connecticut exempts filers below $75k/$100k AGI, New Mexico below $100k/$150k, and Utah phases out a credit above $75k/$100k. The engine does not model these per-state thresholds, so it may **overstate** state tax on Social Security for residents of those 8 states whose income falls below the exemption cutoffs. This is a conservative approximation: it will never understate your state tax bill, and it affects the optimizer's strategy choice only at the margin.

### Step 2 — Planning Assumptions

| Field | What it means |
|-------|---------------|
| **Inflation Rate** | The rate at which your spending needs grow each year (e.g. 3%). The optimizer adjusts your required spending upward by this amount annually. |
| **Nominal Return** | The expected annual return on your portfolio before subtracting inflation (e.g. 6%). The engine uses this to project balances forward. |
| **Medicare surcharge thresholds (IRMAA)** | Two choices: **Allow conversions to cross Medicare surcharge thresholds** (the model includes the surcharge cost) or **Restrict conversions at Medicare surcharge thresholds**. See [IRMAA warnings](#irmaa-warnings) below. |
| **Conversion Window** | Restrict Roth conversions to a specific period (e.g. before Medicare starts at 65, before RMDs begin, or before claiming Social Security). "Anytime" places no restriction. *Before RMDs* closes at your own RMD start age — 73, or 75 if you were born 1960 or later. |
| **Preserve Taxable Accounts** | If switched on, the optimizer avoids drawing down your taxable brokerage accounts first, keeping them available for tax-efficient spending later. |

The less common settings — heir tax rate (what your heirs would pay on inherited traditional-IRA dollars, 25% by default), the Medicare surcharge setting, conversion window and Preserve Taxable Accounts — sit under **Advanced settings**, always shown on the Assumptions step. A **?** beside the Medicare surcharge setting explains IRMAA: a premium surcharge based on income from two years earlier that works as a cliff — $1 over a threshold adds that tier's full surcharge for the year. The optimizer has two surcharge behaviours, so the wizard offers two choices. Plans saved with the older four settings keep their behaviour: *Ignore* and *Soft* show as **Allow**, *Strict* and *Avoid* as **Restrict** (see [IRMAA warnings](#irmaa-warnings)).

### Step 3 — Accounts

Add one row per account. You can have as many accounts as you like. A finished entry collapses to one line — *Traditional IRA / 401(k) · you · $1,000,000* — with **Edit** and **Remove**; **Done** collapses the one you are editing. An entry you are still typing into never collapses on its own. Income entries on the next step work the same way (*Your salary · $100,000/year · 2026–2028*).

> **Tip — upload your portfolio first.** If you upload your holdings on the **Portfolio** tab *before* starting a plan, the wizard reads the total taxable cost basis from it and **auto-fills the Cost Basis field** on this step (you'll see an "Auto-filled from your uploaded portfolio" note; edit it if it's wrong). This saves entering the same figure twice and avoids the common mistake of leaving Cost Basis at 0 — which makes every sale look like 100% gain and overstates your taxes. The auto-fill applies when you have a single taxable account; with multiple taxable accounts the split is ambiguous, so enter each one's basis yourself.

| Column | What it means |
|--------|---------------|
| **Type** | **Taxable** = regular brokerage account (dividends and capital gains taxed annually). **Traditional** = pre-tax IRA or 401(k) (contributions were tax-deductible; withdrawals are fully taxable). **Roth** = post-tax IRA or 401(k) (contributions already taxed; qualified withdrawals are tax-free). |
| **Owner** | Whose account this is (Self, Spouse, or Joint). For a **Traditional** account it decides whose RMD it pays: each spouse's RMD is their own balance at their own age. An IRA cannot be joint, so Joint is treated as yours. (Until October 2026 every Traditional balance took RMDs at your age, whoever owned it.) |
| **Balance** | Current fair market value, in dollars. |
| **Cost Basis** | **Taxable accounts only.** The total amount you paid for the investments (not their current value). **The tax projection uses this to size capital gains**, so leaving it at 0 overstates your taxes. Auto-filled from your uploaded portfolio when one exists (see the tip above). You can also find it on your brokerage statement — look for "Cost Basis" or "Adjusted Cost Basis." If you upload a portfolio *and* type a value here, use the same total in both places; they are reconciled. Basis may be **higher** than the balance — an account at a loss. Sales from it then realize no taxable gain; the loss itself is not deducted (the $3,000-a-year offset against other income and the carryforward are not modelled), so the projection is slightly conservative. |
| **Year Roth opened** | **Roth accounts only; required when the balance is above $0.** The year you first opened this Roth IRA or Roth 401(k), shown on the collapsed line (*Roth · you · $500,000 · opened 2020*). The 5-year rule counts from it: when the plan would withdraw from a Roth within 5 years of that year, the results carry a warning. Copying a plan keeps the year; a plan saved without one asks for it before you can continue. |
| **After-Tax Basis (Traditional)** | If you ever made non-deductible (after-tax) contributions to a Traditional IRA, enter the cumulative amount here. This is tracked on IRS Form 8606 — look at line 14 of the most recent Form 8606 you filed. Without this, the optimizer will assume 100% of your Traditional IRA withdrawals are taxable (the conservative assumption). |

### Step 4 — Income and Social Security

| Field | What it means |
|-------|---------------|
| **Salary / Pension / Rental / Interest / Dividends** | Add any non-Social-Security income. Qualified and non-qualified dividends are entered separately, since they are taxed differently. Enter start and end years when the income is temporary (e.g. a salary that ends at retirement) — the optimizer applies those bounds per year. |
| **Benefit at full retirement age (PIA)** | Your Social Security benefit in today's dollars, at your full retirement age — your *primary insurance amount*. This is the single most important Social Security input. **Where to find it:** Log in at [ssa.gov/myaccount](https://www.ssa.gov/myaccount/) and download your Social Security Statement. Look for "Your estimated benefits" → "At your full retirement age." It is also shown on the paper statement the SSA mails every five years. Do not use the "early" or "delayed" amounts — enter the full-retirement-age figure and let the optimizer handle the timing adjustment. Enter 0 if you have no work record of your own (a spousal benefit can still apply). |
| **Already receiving Social Security?** | Yes or No, asked from age 62. Answer it: a claim already made is fixed and never searched, and the tool will not guess which you mean. **Yes** asks *At what age did benefits start?*, and that age stays fixed. |
| **How should we choose your claim age?** | Asked when you are not yet receiving: **Find the best eligible age** or **Use an age I choose** (see [Claim-age choice](#claim-age-choice)). Claiming before your **full retirement age** permanently reduces the benefit; delaying past it increases it, up to age 70. Full retirement age depends on your birth year: **67** if born 1960 or later, **66 and 2 to 10 months** if born 1955–1959, 66 if born 1943–1954. Survivor benefits use SSA's separate survivor table. |
| **Spouse fields** | The same questions, for your spouse, if filing jointly. They appear once the spouse's benefit is entered. |
| **Social Security COLA** | How fast benefits grow each year, before and after claiming. Blank uses your inflation rate; 0 holds benefits flat. |

#### Claim-age choice

Each person not already receiving benefits is asked how to choose the age, before any age is asked for:

- **Find the best eligible age** — the optimizer tries every eligible age (the range is shown, e.g. *Tries ages 63–70*) and recommends one, together with a conversion strategy. Below it, **Have a claim age in mind? (optional)** takes an age to compare the recommendation with. Leave it at **No comparison** and the results compare conversions at the recommended ages only: no "your ages" comparison is shown, because no age was chosen to compare with — the tool never invents one.
- **Use an age I choose** — an age selector appears, and that age is held fixed. It is required.

Switching between the two keeps the age you entered. A person over 70 who has not yet filed is not asked: they are modelled as filing this year, at the age-70 benefit.

A box beneath, **What the run will compare**, says what the run will do — for example *Compare 64 claim-age combinations · About 4 minutes*, with each person's ages (*You: searching ages 63–70 (compared with 67)*, *Spouse: 67 (already receiving — fixed)*).

**Which ages are eligible.** Every age from 62 (or your current age, if later) to 70, with three exceptions, each stated beside the choice:

- **Already receiving:** locked to the age benefits started.
- **Over 70 and not yet receiving:** modelled as filing now, at the age-70 benefit.
- **A salary still paid before full retirement age:** those claim ages are skipped. Social Security's earnings test would withhold benefits in those years, and this model does not apply it, so it leaves the ages out of the search rather than show a benefit you would not receive. Claiming then is not prohibited. If your comparison age is one of them, it is still scored as the comparison but cannot be recommended.

> **What the claim-age search does and does not model.**
>
> - **Spousal benefits** are applied: a lower-earning spouse receives their own
>   benefit plus the reduced *excess* of 50% of the higher earner's PIA over
>   their own, from the year the higher earner files (SSA's dual-entitlement
>   rule, since October 2026).
> - **Each claim-age pair gets its own conversion strategy.** Claiming later
>   leaves more low-income years for conversions, so the search finds the best
>   schedule for each pair rather than one schedule for all.
> - **Mortality is not sampled.** The ranking assumes you both live to your
>   Plan-to ages, and the simulation varies **investment returns only**. The
>   strongest reason to delay — the survivor keeping the larger benefit — only
>   shows up if one of you dies first, so the search on its own tilts toward
>   claiming earlier. The results' [What if you live longer or shorter?](#what-if-you-live-longer-or-shorter) checks re-score
>   the leading strategies with the plan ending five years earlier or later and,
>   for a couple under 78, with either spouse dying at 78. They are reported,
>   not used to rank: read them as how robust the recommendation is.
> - **Survivor benefits** apply in those death checks and in the What-if page's
>   death scenario: the survivor keeps the larger of the two benefits and loses
>   the smaller. (Until October 2026 the survivor benefit was applied for one
>   year after a death and then overwritten; re-run any death what-if from
>   before then.)
>
> If the claiming decision is large for you, a second opinion is cheap: [Open
> Social Security](https://opensocialsecurity.com) is free, models survivor and
> spousal benefits, and lets you vary mortality assumptions. Where the two
> disagree, those checks usually show why.

### Step 5 — Spending and goals

The goals and caps below (Target Estate, Max Roth Conversion Per Year, Max ordinary-income bracket) sit under **Optional goals and limits**, always shown on the Spending step.

| Field | What it means |
|-------|---------------|
| **How much would you like to spend each year?** | Household spending in today's dollars, excluding income taxes. Enter the full amount before subtracting Social Security or other income; the model calculates income taxes separately. Unless you choose *Cut back, then recover* below, the plan tries to spend exactly this every year regardless of markets — the market simulation shows how often it can. |
| **If markets go badly** | Whether spending is rigid or flexes. See [If markets go badly](#if-markets-go-badly) below. |
| **Minimum annual spending** | *(Cut back, then recover only, optional)* Planned spending cuts will not go below this amount, and spending given up above it is charged at half weight. Left blank there is no minimum: cuts can continue while markets stay poor, and every dollar cut is counted as a full loss. |
| **Target Estate** | An optional bequest goal. It does **not** change which strategy wins. It changes what counts as success: a market scenario counts toward *Spending funded in market scenarios* only if it funds your spending every year *and* ends with at least this much heir-adjusted estate. The comparison is in the dollars of the plan's **final year**, not today's, so inflate a goal you think of in today's money. A run with the market simulation skipped ignores it. |
| **Max Roth Conversion Per Year** | Optional *dollar* cap on how much can be converted in any single year. Useful if you want to spread conversions over more years. |
| **Max ordinary-income bracket** | Optional *bracket* ceiling: never convert past the top of the chosen bracket (e.g. 22% = no conversion that would push ordinary income into the 24% bracket in any year). This is the interpretable version of a per-year cap, and it composes with everything else — pair it with the "Fill the 22% bracket every year" strategy for a plan that fills to exactly that ceiling until the IRA is drawn down. Both caps apply to *every* candidate strategy, not just one. **It caps the bracket, not the cost** — see the note below. |

> **A bracket cap is not a cost cap.** This setting bounds where your *ordinary
> income* lands in the statutory brackets. It does not bound what the marginal
> converted dollar actually costs you, and the two can differ a lot.
>
> Worked example — a retired couple in CA, $60k Social Security, $30k qualified
> dividends, converting $30,000 in 2026. Their statutory bracket is **12%**.
> Converting $1,000 more raises federal tax by $222 and state tax by $20: an
> effective marginal rate of **24.2%**. (The same whether they are 63 or 70:
> the age-65 deductions lower the bill but not this marginal step.)
>
> The reason is the Social Security "tax torpedo": that extra $1,000 of
> conversion pulled a further $850 of Social Security into taxable income, so
> 12% was applied to $1,850, not $1,000. Crossing an IRMAA tier or pushing
> long-term gains out of the 0% capital-gains bracket produces similar jumps.
>
> None of this distorts the optimizer's choices — it scores policies on actual
> total tax, so these effects are already priced in when it ranks plans. But if
> you set this cap expecting "my conversions will never cost more than 12%",
> that is not what it does.
>
> To sanity-check a year's real tax burden, export the spreadsheet and read the
> **effective_rate** column on the Yearly Plan tab. Note that this is an
> *average* rate for the year (total tax ÷ AGI), not the marginal cost of the
> last converted dollar — the figure in the worked example above. The app does
> not currently display that marginal cost directly.

> **A low cap can forbid conversions entirely — check this before concluding
> the optimizer "won't convert".** The cap applies to the bracket your ordinary
> income *already* sits in, not just to the conversion. A couple still earning
> $150,000 of salary is at a 22% marginal rate before converting a cent, so a
> **12% cap forbids every conversion until the salary stops**. The same goes for
> spending drawn from the traditional IRA once the taxable account runs out:
> that withdrawal is ordinary income, so in a year where it passes the 12% top
> on its own, a 12% cap allows no conversion. The optimizer is
> not declining to convert; it was never offered the option. If a run shows no
> conversions and you expected some, look at this setting first, then at
> [Monte Carlo scoring and the shortfall charge](#monte-carlo-scoring-and-the-shortfall-charge).
>
> The cap does permit filling the named bracket to its **exact** top. A
> conversion that lands ordinary income precisely on the 12% ceiling is taxed
> entirely at 12% or less, so a 12% cap allows it — the next dollar after it
> would be taxed at 22%, but no dollar of the conversion is.

### Step 6 — Review and run

The last step asks nothing new. It shows one **summary** — household (with the plan-through ages and the year the projection ends), assumptions, accounts, income, Social Security (claim ages, who is already receiving, and which ages are searched) and spending and goals — each section with an **Edit** link back to its step. If a step was left incomplete, it says which and links to it. Then it states what will be compared: *no conversions, tax-bracket strategies, and fixed annual conversion amounts with different stopping years*, with those amounts in dollars (5%, 10% and 20% of your starting traditional balance). Below it is a single action, named for what it runs:

- **Optimize conversions** when every claim age is fixed;
- **Optimize conversions and claim ages** when at least one is searched, with the number of claim-age combinations and an estimate of the time.

See [Running the optimization](#running-the-optimization) for what happens next.

### If markets go badly

This is the one setting that changes what a *plan* is, rather than what the
optimizer prefers within it.

**Keep spending the same** (the default) spends your annual spending
every year, inflated, no matter what markets do. It is the strict test: can
this plan survive without you changing your life?

**Cut back, then recover** models what retirees actually do, using the
Guyton-Klinger guardrails:

- Each year the plan measures the **withdrawal rate** your portfolio has to
  carry — that is, spending *minus* Social Security and pensions, divided by the
  portfolio. A large pension means you are not overspending just because your
  small portfolio shows a high percentage.
- If that rate drifts more than **20% above** where it started, spending is cut
  **10%**. If it drifts 20% below, spending is restored 10%.
- **Cuts persist** and are held in real terms, so a 10% cut stays a 10% cut
  rather than being inflated away.
- Spending **never falls below your Minimum annual spending**, and **never
  rises above your target**. (Guyton-Klinger's original rule keeps raising
  spending in good markets. You told the tool what you *need*, not what you
  would enjoy, so restoration stops at your number.)

**What this changes about your results, stated plainly.** Guardrails raise
success probability, because a plan that cuts its way through a bad decade does
not fail. On a test household they moved it from **14% to 38%** — while
reducing spending in an average of **21 of 30 years** (measured in August
2026; see [Example 2](#example-2--what-running-out-of-money-actually-costs)). Both halves of that
sentence are true, so the results page shows both: the *Spending funded* card
carries a *"Spending below target in approximately 21 years per simulated
path"* note, a line beneath the cards explains that with guardrails on those
years include the planned cuts, and the year table marks each reduced year. A
funded path then means *"never failed to fund the reduced spending"*, not
*"always funded your full target"*.

The cuts are also **charged in the score** at half weight (see [Monte Carlo
scoring](#monte-carlo-scoring-and-the-shortfall-charge)) — spending you gave up
is not free just because you chose it.

> **Known characteristic.** The withdrawal rate is measured against *gross*
> Social Security and pension income, because the tax on it depends on
> withdrawals that have not been solved yet. That makes the measured rate
> slightly low and the guardrails slightly slow to trigger. The same
> approximation sets the year-one anchor the rule compares against, so the
> comparison largely cancels — but if you retire several years before claiming
> Social Security, your anchor is set in a year when the portfolio carries the
> whole load, and the guardrails will start correspondingly wide.

---

## Running the optimization

**With every claim age fixed**, the Review step's **Optimize conversions** runs
the plan straight away — under a minute — and opens its results.

**With at least one claim age searched**, **Optimize conversions and claim ages**
starts a background search, because it scores a conversion strategy for every
claim-age pair (64 pairs for a couple who can each claim at 63–70) and takes a
few minutes. You are taken to its progress page, which shows each stage as it
runs:

1. **Compare strategies** — every claim-age pair's strategies on the
   steady-return projection, counted in claim-age pairs;
2. **Test market outcomes** — the leading candidates under the market
   scenarios, counted in batches;
3. **Check longevity** — the lifespan checks;
4. **Prepare results** — the saved run.

You can leave the page: the search continues while the server runs, and the
header shows **Search running · View progress** on every page until it is
done. When it finishes, the progress page opens the results; if you have left
it, the plan's **View results** on the dashboard opens them. One search runs at a time: if another is already
running, the Review step says so, links to its progress, and leaves your plan
unsaved until you start it again. (If the other search started in the moment
after your plan was saved, the Review step says so; start it again there and
the plan is not saved a second time.)

Searches live in the server's memory. If the backend is stopped mid-search,
nothing is saved and the progress page says so, with **Run again** to start it
over.

**The dashboard** shows each plan's name and latest run, one action for the
plan's state, and a trash icon, **Delete plan**, which asks for confirmation.
The action is **View results** (the plan's latest optimized run), **View
progress** while its search runs, or — for a plan saved but never run, for
example when another search was already running — **Finish setup and run**.
That opens Review for the same plan: running it reuses the saved plan (updated
in place if you edit it), never a copy, and keeps the claim-age choices you
made. Those choices are recorded in the browser that saved the plan; elsewhere,
Review asks you to confirm any it cannot deduce (a blank comparison age can
only mean *Find the best eligible age*) rather than assume them. What to optimize is chosen in the wizard: to change a plan's
inputs, start a **New Plan** copied from it, or try a change on the **What-if**
page. **Portfolio** is in the top bar only: your holdings are uploaded once and
shared by every plan.

---

## Reading the Results

The results page reads top to bottom: the recommendation, how it compares with your original choices,
the close alternatives, then — for a claim-age search — **Explore other Social
Security claim ages** and **What if you live longer or shorter?**, and finally
the charts, the year-by-year plan and the inputs. Exploration sections start
collapsed, each with a one-line summary.

### Two kinds of number

Every figure on the page says which of two bases it comes from. A box beneath
the summary cards, **How we simulate market outcomes**, explains both with the
run's own recorded assumptions:

- **Market scenarios** — the plan tested under 300 (by default) possible
  investment-return sequences. Returns vary from year to year, gains and
  losses, around your assumed average return; every strategy faces the same
  scenarios, so comparisons are fair. Each year's return is drawn
  independently from a normal distribution with an annual volatility (standard
  deviation) of 12 percentage points — the box states the figures the run
  recorded. The **modeled score** and the share of **scenarios with spending
  funded** come from these, and they are what the recommendation is chosen on.
- **The steady-return projection** — a projection assuming every year earns
  exactly your assumed average return. The **projected estate**, **lifetime
  taxes**, the charts and the year-by-year table come from it. It is not the
  median of the market scenarios.

Runs saved before October 2026 did not record their volatility; the box then
gives their average return and leaves the volatility unstated. A run made
without the market simulation (from the API with `monte_carlo_runs: 0`) says
**No market simulation** in its place and has no comparison results: it was
decided on the steady-return projection alone.

### The recommendation

A banner leads with the decision:

- **Recommended strategy** above the plan's name — or *Strategy you chose to
  run* on an older forced-strategy run (see [Older forced-strategy
  runs](#older-forced-strategy-runs)).
- For a claim-age search, the ages: *Claim Social Security at 70 (you) and 67
  (spouse)*. A fixed-age run states the ages it used.
- The conversions: *Fill the 12% bracket through 2031: $612,000 converted in
  total, the last in 2031; $98,450 this year* — or *No Roth conversions in this
  modeled plan.*
- One sentence on how clearly it leads: for example *Highest modeled score, and
  ahead of each close alternative across the market scenarios*, or *Highest
  modeled score. One alternative is practically equivalent: …*.

Four cards follow:

| Card | What it means |
|------|---------------|
| **Spending funded in market scenarios** | The share of scenarios in which the plan funded its spending every year, with its sampling margin and scenario count — *96% · ± 2 pts (300 scenarios)*. Read it as a band, not a point. When spending fell below target in some years, a note gives the average count: *Spending below target in approximately 3 years per market scenario.* With guardrails on, a separate line explains that those years include the planned cuts. |
| **Modeled score** | The average after-tax estate across the market scenarios, minus penalties for spending the plan could not fund — *Today's dollars · 300 market scenarios*. It is not tax saved or extra estate; **How the modeled score is built** breaks it down. |
| **Projected estate at a steady 6% annual return** | The estate at the end of the plan, in final-year dollars, assuming the run's average return every year, with *Equivalent to … today* beneath it. That today's-dollar figure is the same estate discounted, not a second projection. |

The modeled score and the estate's today's-dollar value differ because they use
different returns — varying across the scenarios versus steady — and the score
also subtracts spending-shortfall penalties. A higher score does not mean the
optimizer created that much extra wealth: these are different measurements,
not an improvement.
| **Lifetime taxes — steady-return projection** | Federal and state tax plus Medicare surcharges over the whole plan, in nominal dollars, with the present value (2% a year discount) beneath it. |

Advisories sit below the cards. When an alternative funds spending in more
scenarios, or scores higher in some lifespan checks, a short note says so: the
recommendation is ranked on the modeled score, not on that share alone.

### Recommended strategy compared with your original choices

Each comparison is stated as *from → to* — for example **Your ages 65 / 63 →
Recommended ages 69 / 68** — with a sentence and a small table that show both outcomes
and the difference:

> Changing your claim ages from 65 / 63 to 69 / 68 improves the modeled result
> by $153,776. Spending is funded in 294 of 300 market scenarios, compared with
> 284 using your entered ages. Neither strategy makes Roth conversions.

| Across the same 300 market scenarios | Your ages: 65 / 63 | Recommended ages: 69 / 68 | Difference |
|---|---|---|---|
| Average modeled score | $2,847,044 | $3,000,820 | +$153,776 |
| Average after-tax estate | $2,862,534 | $3,004,868 | +$142,334 |
| Average unfunded spending | $15,490 | $4,048 | −$11,442 |
| Scenarios with spending funded | 284 of 300 | 294 of 300 | +10 |

The modeled score is the after-tax estate minus spending-shortfall penalties,
so the estate and unfunded-spending rows add up to the score difference. It is
neither tax saved nor a guaranteed increase in your estate. A claim-age search
shows up to three comparisons:

| Comparison | From |
|---|---|
| Your ages → Recommended ages | Your comparison ages, with their best conversion strategy |
| No conversions → the recommended strategy | The recommended ages, with no conversions |
| Your ages without conversions → Recommendation | Your comparison ages, with no conversions |

When there is nothing to compare — no comparison claim ages and a
recommendation that makes no conversions — the section is not shown; a single
line says *No comparison claim ages were provided.*

A fixed-age run has only the conversion comparison. The comparisons overlap —
the last already contains the other two — so do not add them. When there is
nothing to measure (the recommendation converts nothing, or your entered ages
are the recommended ones), a line says so instead. Runs saved before October
2026 lack the estate and unfunded-spending rows.

### Close alternatives

The strategies nearest the recommendation, each tested on all the market
scenarios. For a claim-age search the list includes every finalist, with its
claim ages (*claim at You 70 · Spouse 69*). The main table ranks them the way
the optimizer did, by the modeled score across the market scenarios, with the
recommendation first:

| Column | Meaning |
|---|---|
| Average modeled score | each strategy's own average across the scenarios, in today's dollars |
| Difference from recommendation | its average minus the recommendation's, on the same scenarios; **negative = scored lower** |
| Scenarios with spending funded | each strategy's own count, e.g. *293 of 300* |
| Comparison result | the scenario-by-scenario label (see [Comparison labels](#comparison-labels)) |
| Roth conversion in 2026 | shown when some strategy converts in the projection's first year: the amount transferred from traditional to Roth accounts that year |

When some alternatives are *Too close to distinguish* or *Practically
equivalent*, an amber line above the table names them: *Ages 69 / 68 have the
highest average modeled score. However, this simulation cannot clearly separate
them from ages 68 / 67, 68 / 66 or 68 / 65.* The recommendation's banner says
the same. That label does not mean the alternatives are worse, and it does not
mean they are equivalent.

**Compare taxes and estate assuming a steady 6% return** (collapsed, with the
run's own return) holds each alternative's tax difference (present value;
**negative = pays less tax**) and estate difference (**positive = leaves
more**) on the steady-return projection. Close alternatives often look better
there — less tax, more estate — yet rank lower, because the ranking reflects
how each strategy holds up when returns vary. **How these comparisons work**
explains this. A run without a market simulation, or one saved before paired
comparisons, keeps the single table of tax, estate, funded share and
conversion. A strategy set aside early in an older search was scored on fewer
scenarios; a note says so.

**When the first year's amount is not settled.** Close strategies tend to agree
on roughly how much to convert *in total* and disagree on how much to convert
*now*. When some alternatives are *Too close to distinguish* or *Practically
equivalent*, an amber note gives the range of the first year's conversion
across them and the recommendation — *the recommendation converts $208,200 in
2026, but the strategies the simulation cannot distinguish from it convert
anywhere from $208,200 to $502,550*. Treat the amount as a range and compare
its ends on the [What-if page](#the-what-if-page) before you act. If none of
them converts anything that year, the note says so and lists the year each
starts.

The list is for reading: nothing on the results page starts another
calculation. To see a different strategy or claim age in full, use the What-if
page, or copy the plan, change the input and run it.

### Comparison labels

Each alternative is compared with the recommendation **scenario by scenario** —
the same market sequence run through both, the difference taken — which
cancels most market noise. The comparison result is one of four labels:

| Label | Meaning |
|---|---|
| **Recommendation ahead** | The recommendation's lead is established: its 95% interval excludes zero and the median difference has the same sign. |
| **Alternative ahead** | The same, in the alternative's favour. It appears on older forced-strategy runs, where the plan shown was not chosen on score. |
| **Practically equivalent** | The results are similar enough to treat these options alike under the model's comparison threshold: the whole interval lies within ±$5,000 or 0.25% of your assets, whichever is larger. |
| **Too close to distinguish** | These simulations don't give us enough evidence to say which option is better: the interval includes zero but reaches beyond that threshold, or the average and the median difference point different ways. More scenarios might separate them; it is not a claim that they are equal. |

The figures behind a label — the average difference and its interval — are in
the label's tooltip. **What the comparison labels mean**, beside Close
alternatives, gives each label's plain meaning, with the interval, median and
dollar threshold under **Technical details**. *Practically equivalent* and *Too
close to distinguish* stay separate: the first is evidence of a small
difference, the second is not enough evidence to settle the comparison.

### Explore other Social Security claim ages

*(Claim-age searches only; collapsed.)* The summary line says what was done —
*We compared 48 combinations of your and your spouse's claim ages using 50
market scenarios. We then tested the 5 leading strategies, along with your
baseline options, using 300 market scenarios.* The initial 50 scenarios are
included in the final 300; there are not 350.

The grid shows that initial comparison: your ages down the side, your spouse's
across. Each cell shows the pair's best strategy and its score against the
recommendation on the same 50 scenarios (a strategy shared by most cells is
named once, in the legend). The recommended pair is tagged **Recommended
ages**; your entered ages are outlined; ages that could not be searched are
greyed and listed below with the reason. A strategy that looks better in the
grid may rank lower when tested using all 300.

Select a cell to inspect its results; this does not start another calculation.
The panel shows the claim ages, the strategy, and how it compares with the
recommendation — or, for a pair that was not carried forward, *Screened during
the search; not selected for detailed comparison.* Scenario counts and the
separate figures are under **Technical details**, as is the note on the
two-year income look-back Medicare uses (it is the same for every claim pair).
Runs saved before the recommendation's initial-comparison score was stored say
*Screening comparison unavailable for this saved run* rather than compare
figures from different numbers of scenarios. A single filer sees the same
information as a list of ages.

### What if you live longer or shorter?

*(Claim-age searches only; collapsed.)* The leading strategies re-scored under
different lifespans, with each strategy's rule and stop year unchanged: the plan
ending **5 years earlier**, **5 years later**, and, for a couple under 78, **you**
or **your spouse dying at 78**. One row per strategy, one column per check: the
recommendation's row shows its modeled score under each check, the others their
difference from it under the same check. The last row, **Highest among the
strategies checked?**, says Yes or No per check.

These checks are reported, not used to rank. A recommendation that stays highest
across them is robust to how long you live; one that does not is worth reading
alongside the strategy that overtakes it, which the summary line names.

### Charts

All three charts follow the steady-return projection, and dashed markers show the
years that shape them — a salary ending, each Social Security claim, and the
first RMD — also listed in text above the charts. A claim in the first year of
the plan is marked only when that person is not already receiving benefits.

**Account Balances Over Time** — Taxable, Traditional and Roth balances year by
year. A healthy trajectory typically shows Traditional declining (from
conversions and RMDs) while Roth grows.

**Tax Breakdown** — stacked bars of federal income tax, state tax, and Medicare
(IRMAA) premiums per year. Large spikes often coincide with RMD years.

**Roth Conversions** — the conversion in each year. A plan with no conversions
shows a one-line note instead of an empty chart.

### The Year-by-Year Table

Each row represents one projection year and shows:
- Starting balances (Taxable, Traditional, Roth)
- RMD amount (0 before your RMD start age — 73 if born 1951–1959, 75 if born 1960 or later)
- Roth conversion amount
- Total taxes
- Net spending funded
- Bracket room left (see below)
- Ending balances

Each row has an expand button (▸) — keyboard-accessible — that opens the
**Rationale Panel** for that year.

### Inputs

At the bottom, the inputs the run was made with, in two columns: household,
accounts, income (with the years each source is paid), Social Security, and the
assumptions, with the method and tax tables on full-width rows. Social Security
amounts are labelled as the benefit at full retirement age, and each claim age
says where it came from — *Entered 69 · searched · recommended 69*, *Held
fixed at 67*, or *Already receiving (claimed at 66)*.

**Bracket Room.** How much more ordinary income fits in the federal bracket the
year lands in before the next rate applies — the room a further Roth conversion
could use. *"$33,000 left in 12%"* means you could convert another $33,000 at
12%. A bracket-fill year reads *"$0 left in 10%"*. Marginal % beside it is the
rate on the *next* dollar, so that same year shows 12% there: the 10% bracket
is full and the next dollar would be taxed at 12%. The top bracket shows "—".
The Excel and CSV exports carry the same figures as `bracket_rate` and
`bracket_room_left`.

**Reduced years.** With guardrails on, a year in which the rule trimmed
spending shows the amount in amber beneath Net Spendable — *"$22,000 below
target"*. This is not a failure: the plan funded what it set out to fund. It is
spending you gave up, shown because the alternative is quietly lowering the bar
the plan is being judged against.

**Underfunded years.** The table always runs to the end of your horizon, even
when the projection says the money runs out first. When a year cannot cover
required spending after every account has been drawn down, its Net Spendable
figure turns red and carries the gap beneath it — *"$29,000 short"*. Those rows
show what your guaranteed income alone would cover, after tax. They are the
years worth planning around, so the table shows them rather than stopping.
(Before August 2026 the table simply ended at that point, which looked like a
display fault.)

### Rationale Panel

The rationale panel explains, in plain English, what the plan does in each year and why — which bracket a conversion filled, what IRMAA threshold was approached, and what each converted dollar cost.

**A year with no conversion states the reason the strategy gives**, and only a
reason the plan establishes: the strategy makes no conversions; it starts
converting in a later year; it converts only through an earlier year; its last
conversion has already happened; nothing is left in traditional accounts; or
its rule found no room that year. A year's RMD is named as the cause only when
the RMD and other income leave no room in the bracket; otherwise the RMD is
stated as a fact (*This year's required minimum distribution is $32,000*).
Runs saved before October 2026 stored a vaguer sentence — *either the
conversion window is closed, or …* — and the results page restates those years
with the known reason; their exports keep the stored text.

A conversion that fills a bracket to its top is labelled with **that** bracket — *"filled the 12% bracket"* — not the next one up, and the remaining headroom is measured on taxable **ordinary** income (qualified dividends and long-term gains do not use up bracket room). Runs saved before 26 September 2026 store the older wording, which could name the bracket above and overstate the room; re-run the plan to refresh them.

**Warning badges** appear when a threshold is near or crossed:
- **Amber badge** — a threshold is close but not crossed (e.g. within $5,000 of the next IRMAA tier).
- **Red badge** — a threshold was crossed (e.g. a conversion pushed income into a higher IRMAA tier).

### IRMAA Warnings

IRMAA (Income-Related Monthly Adjustment Amount) is an extra Medicare Part B and Part D premium charged to higher-income retirees. It is based on your income from **two years prior** (e.g. 2027 premiums depend on 2025 MAGI).

The tiers jump discontinuously — a $1 increase in income can add hundreds of dollars in annual premiums. The Medicare surcharge setting (Step 2, Advanced settings) controls how the optimizer handles these cliffs:
- **Allow conversions to cross Medicare surcharge thresholds** — the surcharge is counted as a cost, for each of you on Medicare, and a conversion may cross a tier when the tax it saves is worth more. (Plans saved with the older *Ignore* or *Soft* setting behave this way.)
- **Restrict conversions at Medicare surcharge thresholds** — a conversion that would push the year's income over the next tier is dropped. Converting nothing is always an option, so "stay below whenever possible" and "never cross" are the same rule. A tier your income reaches *without* converting can't be avoided by not converting; the guard is against the next one up. (Plans saved with the older *Strict* or *Avoid* setting behave this way.)

Whatever the setting, the surcharge is always charged for every person on Medicare. (Until October 2026 *Ignore* left the surcharge out of the plan altogether, it was only charged while **you** were on Medicare — so a spouse who reached 65 first paid nothing — and *Strict* behaved like *Soft*. Re-run plans that used *Ignore*, or where your spouse is older than you.)

### BETR — Break-Even Tax Rate

BETR (Break-Even Tax Rate) answers the question: "What future tax rate would make a Roth conversion break even?" If your BETR is 28% and your projected future marginal rate is 32%, the conversion is **favorable** — you are paying 28% now to avoid 32% later. If your BETR is 28% and your projected future rate is 22%, the conversion is **unfavorable**.

The BETR methodology follows Vanguard's framework: Vanguard, "A BETR approach to Roth conversions," July 2025. Its horizon — how many years the converted money grows before RMDs would have forced it out — runs to your own RMD age: 73, or 75 if born 1960 or later (before October 2026 it assumed 73 for everyone).

**Why BETR often reads "unfavorable" even for the winning strategy.** BETR is a **single-year** diagnostic, and it compares against **one** projected future marginal rate. Two things make it lean "unfavorable" for many near-retirees:

1. **This year's cost is inflated by cliffs.** The conversion's cost includes any IRMAA surcharge and NIIT it triggers *this* year. Those are one-time, cliff-shaped costs, so a single conversion year can look very expensive (e.g. 33%+), pushing BETR up.
2. **The "future rate" is a single number.** It's the marginal rate the no-conversion path would hit once RMDs begin — but your real future cost is *decades* of RMDs stacking with Social Security taxation and IRMAA, which a single percentage understates.

So the per-year BETR can say "unfavorable" while the **lifetime** simulation — which the optimizer actually uses to choose the recommendation — still converts, because over the full horizon the conversion lowers total taxes (or grows the estate). When the break-even rate and the recommendation disagree, **trust the lifetime comparison** (the modeled score, the comparison with your original choices and Close alternatives); BETR is a rule-of-thumb sanity check for a single year, not the decision.

---

## How the Optimizer Works

> Engineering companion: **[`OPTIMIZER_INTERNALS.md`](OPTIMIZER_INTERNALS.md)** documents the
> same pipeline against the code — every candidate policy and where it comes from, the
> two separate rankings, the staged Monte Carlo budget, the joint claim-age search, the
> per-year funding solver and its convergence behaviour, and measurements of what does
> and does not move the recommendation.

### The objective

For every candidate strategy, the optimizer simulates your **entire planning horizon year by year** using the real tax engines (federal, state, IRMAA, RMD, Social Security), then scores the strategy on a single formula:

> **score = PV(terminal estate, heir-adjusted) − 1.0 × PV(unfunded essential spending) − 0.5 × PV(spending cut above your floor)**

- **Heir-adjusted** means a traditional-IRA dollar counts at (1 − heir tax rate) — 75¢ by default — while Roth and taxable dollars count at 100¢, because heirs owe income tax on inherited traditional IRAs. This is what gives Roth conversions credit for making an estate more tax-efficient, not merely for lowering the tax line.
- **Present value (PV)** discounting means a tax dollar paid this year hurts more than one paid twenty years from now. A strategy that prepays tax must earn that money back.
- **Taxes are not subtracted separately.** Every tax dollar has already left the accounts, so the estate is net of it. The formula used before October 2026 subtracted present-valued lifetime taxes *as well*, counting them twice, and its *Lifetime taxes* priority rewarded any plan with less income — including a smaller Social Security benefit — simply because it paid less tax. Lifetime taxes are still shown on every result.
- **The same formula ranks strategies in the single-path search and in Monte Carlo**, with the same shortfall weights. Each result states what its score is made of.
- **Runs saved before October 2026** keep their *Optimization Priority* label on the results page and in exports; their scores were computed under the old formula.
- **Monte Carlo** then simulates each candidate across many randomized market scenarios rather than a single return path — this is the actual ranking basis, not just a tiebreak. See [Monte Carlo scoring and the shortfall charge](#monte-carlo-scoring-and-the-shortfall-charge) below.

One clarification worth stating: the **Preserve Taxable Accounts** switch controls *withdrawal order only* (spend taxable first vs. spend the IRA first to leave step-up-basis assets for heirs). It does **not** change what the optimizer maximizes.

### Monte Carlo scoring and the shortfall charge

The formula above is computed for a *single* assumed return. A real plan faces an unknown **sequence** of market returns, so the optimizer does not rank strategies on one return path — it runs each candidate through **300 Monte Carlo scenarios** and scores it on the *distribution* of outcomes. The budget is spent adaptively: every candidate is scored on a cheap first slice, then only the strategies still in contention are carried to the full count — by *extending* the same set of scenarios, never regenerating it, so the comparison stays paired.

- **Each scenario** draws an **independent return for every year** from a bell curve centered on your Expected Return with a **12% annual volatility**, then re-simulates the entire plan on that year-by-year path. That produces one value of the objective above per scenario. (Every strategy sees the *same* return sequences, so the comparison is fair — and strategies are compared scenario by scenario, which is far more precise than comparing their averages separately.) Drawing returns *per year* — rather than one return held constant for the whole horizon — is what makes this a real **sequence-of-returns** model: a bad year is offset by other years, so the 27-year *average* return clusters near the mean (its spread is roughly the annual volatility ÷ √years). This is why a comfortably funded plan reads a **high success probability** (often ~99%) rather than being dragged down by a hypothetical run of bad years that never reverts.
- **The ranking score charges unfunded spending, not volatility:**

  > **ranking score = average( PV(heir-adjusted estate) − λ × unfunded spending )**

  For each scenario the optimizer computes the economic value above, then
  subtracts the present value of any retirement spending that scenario fails to
  fund. **λ (the shortfall weight) is 1.0**: a present-value dollar of unfunded
  retirement costs one dollar of economic value. **Success probability** — the
  share of scenarios that fund every year — breaks any remaining ties.

  **If you let spending flex, the flex is charged too.** With guardrails on
  (see [If markets go badly](#if-markets-go-badly)), the consumption gap is
  charged in two tiers, split at your essential floor: a dollar given up while
  still *above* the floor costs the objective **50¢**, and a dollar you cannot
  fund *below* it costs the full **$1**. The split is by dollar level, not by
  cause — a guardrail cut and a year the money ran out are the same loss to the
  person living it.

  Why the discretionary tier exists at all: if a voluntary cut cost nothing,
  the optimizer would read "spend less" as free safety and every plan's score
  would improve for a reason no retiree would call good news. Charging it at
  half weight is what makes flexibility genuinely valuable rather than either
  free or pointless. With no floor set, the second tier is always empty and
  the scoring is identical to the strict fixed-spending reading.

  **A short year is charged for what it misses, not for missing.** Every
  scenario is simulated to the end of your horizon even after the portfolio is
  exhausted, because Social Security and pensions keep arriving and still get
  taxed. A year that needs $213,934 and can still put together $140,860 is
  charged **$73,073** — not the whole $213,934 — and the years after it are
  charged what *they* actually miss rather than being written off in full. On
  the household in [Example 2](#example-2--what-running-out-of-money-actually-costs)
  that cut the charge from $1.32M to $950,000, removing a **39%**
  overstatement. Because the post-depletion years are really simulated, the
  relief from guaranteed income is counted **after the tax on that income**,
  which is what makes "one unfunded dollar costs one dollar" literally true
  rather than aspirational.

  One present-value dollar of unfunded essential spending costs exactly one
  dollar of estate: a plan cannot buy estate by leaving spending unfunded, and
  cannot buy a lower tax bill by running out of money.

> **Changed August 2026.** The ranking formula above replaced an older one, as
> part of a five-part rebuild of how strategies are compared. See
> [How the ranking was rebuilt](#how-the-ranking-was-rebuilt-august-2026) for
> the whole story. **Plans created before this change may rank strategies
> differently now; the tax calculations are unaffected.**

**Why this matters when you read your results.** The taxes and estate shown on the results page and in Close alternatives come from the **steady-return projection**, in which every year earns exactly your assumed average return. It is not the median of the market scenarios; no scenario is picked out to show. The *ranking* is the modeled score, the average across all scenarios net of unfunded spending. For a well-funded plan these agree, and the recommendation is also the best on the numbers shown. But for a plan with real shortfall risk, the average is pulled down by how badly a strategy runs out of money in the **worst** scenarios — so there a strategy can show lower taxes or a larger estate in the steady-return projection yet still rank **below** a more resilient recommendation. When that happens the recommendation is the more **robust** choice, not the lowest-tax one in the lucky case.

**How precise is the share of scenarios with spending funded?** Less than a single number suggests, which is why the results page prints the margin next to it. At 300 scenarios a reading of 70% carries roughly **±5 percentage points**; at the old 100 it was ±9, and re-running with a different random seed moved it 6–8 points. Read it as a band, and treat small differences between strategies as noise rather than signal.

**Comparison labels.** Every alternative is compared with the recommendation path by path and labelled *Recommendation ahead*, *Alternative ahead*, *Practically equivalent* or *Too close to distinguish* — see [Comparison labels](#comparison-labels). *Too close to distinguish* does **not** mean the two are equivalent; it means the simulation does not clearly separate them. The optimizer reports this rather than presenting a coin flip as a ranking.

**One fixed dial (not yet user-configurable).** The **12% volatility** is a constant in the engine, chosen as a reasonable default from the project's design spec. λ is also fixed at 1.0 today, though unlike the old risk-aversion weight it has a defensible interpretation at that value.

**Is the 12% volatility realistic?** As a rough proxy, yes — it corresponds to a moderate **~60/40 stock-bond portfolio**, which historically runs about 10–12% annual volatility. Rough reference points:

| Portfolio mix | Typical annual volatility (σ) |
|---|---|
| 100% US stocks | ~15–20% |
| **60/40 balanced** | **~10–12%** |
| Conservative 30/70 | ~7–9% |
| All bonds / cash | ~3–6% |

The 12% also **pairs sensibly with the tool's default 6% nominal return**: a 60/40 portfolio's long-run expected nominal return is roughly 6–7%, so the two defaults describe the *same* balanced retiree portfolio. Caveats worth keeping in mind: it is a single blanket figure regardless of your actual allocation (hold much more stock and your real risk is *understated*; hold much less and it is *overstated*), it is applied to every account with no separate stock/bond split, and the bell-curve shape understates real-world crash risk. So read the success probability as calibrated to a balanced portfolio — and as somewhat optimistic if you are heavily in equities.

### How the ranking was rebuilt (August 2026)

Five changes landed together. They do not touch the tax engines — every federal,
state, IRMAA and RMD calculation is exactly what it was. What changed is how the
tool *compares* strategies and *reports* the comparison. In plain terms:

**1. It stopped punishing good luck.**
The old score subtracted half the standard deviation of the outcome — a measure
of how spread out the results were. But spread is symmetric: it counted a
scenario where you die with an unexpectedly *large* estate as a bad thing, right
alongside one where you run out of money. No retiree holds that preference. The
penalty is now on the thing people actually fear: **spending you cannot fund**.

*Why you should care:* that one hardcoded number was strong enough to flip a
plan that converted **$769,663** into one that converted **nothing**. It was
outvoting the tax law.

**2. It says when two strategies are too close to call.**
Strategies are now compared **scenario by scenario** rather than by their
averages — the same market sequence, run through both plans, difference taken.
Most market noise cancels, which made the comparison about **four times more
precise**. When the remaining uncertainty still spans zero, the tool says
*"too close to call"* instead of picking a winner.

*Why you should care:* it will no longer tell you strategy A beats strategy B
because A scored $2,137 higher in a simulation whose margin of error is
$40,000. And *too close to call* — labelled *Too close to distinguish* since
October 2026 — is not the same as *equivalent*: it means the simulation cannot
separate them, which is a different and more honest claim.

**3. It runs three times as many scenarios, without taking three times as long.**
Every candidate is scored on a cheap first slice; only the strategies still in
contention are carried to the full count — by *adding* scenarios to the same
set, never re-rolling it, so the pairing from change 2 is preserved.

*Why you should care:* the success probability used to move **6–8 points** just
from the random seed. Reading "70.0%" implied a precision that was not there.
It is now shown as a whole number with its margin: **70% ± 5 pts**.

**4. A year that falls short is charged for what it misses, not for missing.**
The projection used to stop dead at the year the money ran out, and charge every
remaining year's full spending as lost. But a year that needs $213,934 and can
still assemble $140,860 has not lost $213,934 — it has lost $73,073. And the
years after it still receive Social Security, which is still taxable. Every year
is now simulated to the end of your horizon, and each is charged only its own
gap.

*Why you should care:* the old method overstated the damage by **39%** on the
household in Example 2 below. Your year-by-year table also no longer just stops
— it runs to the end, showing what income alone would cover in the lean years.

**5. You can tell it you would cut back — and cutting back is not free.**
The new [If markets go badly](#if-markets-go-badly) setting lets spending flex
with the markets instead of staying rigid. The important half is that a
voluntary cut is still **charged** to the score, at half the weight of spending
you cannot fund at all.

*Why you should care:* if cuts were free, the tool would treat "spend less" as
costless safety and every plan's score would improve for a reason you would not
call good news. Half weight is what makes flexibility genuinely valuable rather
than either free or pointless.

---

#### Example 1 — the hidden dial that was deciding the answer

A household is deciding whether to do Roth conversions. Under *Lifetime taxes*
priority — where the tool's only job is to minimise total tax — the fully
simulated results were:

| Strategy | Lifetime taxes (nominal) |
|---|---|
| Convert into the 32% bracket | **$513,529** |
| Convert into the 24% bracket | $519,521 |
| Convert ~10% of the IRA a year | $537,558 |
| **Convert nothing** | **$1,168,339** |

Converting saves roughly **$650,000**. Yet the tool recommended converting
**nothing**.

The reason was the old variance penalty. Outcome spread for this household ran
about **$987,000** — the same order of magnitude as the entire tax signal — so
subtracting half of it swamped the $650,000 and reversed the answer. Nothing in
the interface mentioned this, and there was no setting to change it.

With the penalty on unfunded spending instead of spread, the recommendation
flips back to converting — **$769,663** for this household when the change was
measured. (Changes 4 and 5 later reduced the shortfall charge further, which
pushes in the same direction, so the exact figure for any given plan today may
differ; the reversal does not.)

> **What to take from this:** if you ran a plan before August 2026 and it told
> you not to convert, it is worth re-running. The recommendation may change, and
> the tax arithmetic behind it was never in question.

#### Example 2 — what running out of money actually costs

A couple aged 63 and 61 in California, **$1.6M** across their accounts, spending
**$115,000** a year over a 30-year plan. (Figures as measured in August 2026;
the October corrections move them somewhat, not the lesson.) If they never convert, the projection
says the portfolio empties in **2047**.

The old method stopped the projection dead at that point and charged every
remaining year's full spending as lost — **$1.32M** in present-value terms. But
look at what actually happened in 2047:

| | |
|---|---|
| Spending needed that year | $213,934 |
| What the plan could still assemble | $140,860 |
| **Actually unfunded** | **$73,073** |

That year was **two-thirds funded** and was booked as a total loss. Counting each
year's real gap — and continuing to simulate the later years, where Social
Security keeps arriving and keeps being taxed — brings the true figure to
**$950,000**. The old method overstated it by **39%**.

Now the same couple turns on **Cut back, then recover** with an $85,000
essential floor:

| | Keep spending the same | Cut back, then recover |
|---|---|---|
| Success probability | 14% | **38%** |
| Years spending fell below target *(average per scenario, of 30)* | 9.2 | **21.1** |
| Roth conversions recommended | $235,221 | **$282,422** |

Flexibility more than doubles the odds of the plan surviving — **and costs about
21 of 30 years at reduced spending**. Both halves of that sentence are true, so
the tool shows both: the success card carries the years-reduced figure, and the
year table marks each reduced year.

The third row is the subtle one. Because spending can now give way in a bad
decade, the plan can afford to convert **$47,000 more** — the flexibility buys
room for tax planning, not just survival.

> **What to take from this:** a high success probability with guardrails on is a
> weaker claim than the same number with them off. It means *"the plan never
> failed to fund the spending it allowed itself"*, not *"you always got what you
> asked for."* Read it alongside the years-reduced figure, never on its own.

#### What did not change

The rationale panels — the plain-English explanation on each year, the
break-even tax rate, the cost per converted dollar — were not touched by any of
this. If those look different to you, it is because the tool is now recommending
a **different strategy**, so there are different decisions to explain, and
because the table runs to the end of the horizon instead of stopping early, so
there are more years to open. (The rationale panel's own improvements — the
honest conversion wording, the all-in cost per dollar converted, the neutral
break-even framing — shipped separately, just before this work.)

### The October 2026 corrections

In October 2026 a set of calculation errors was found and fixed together. Unlike the August rebuild, several of these **do**
change tax and balance figures, not only the ranking. Plans made before
**16 October 2026 should be re-run**; saved runs keep their old numbers.

**Changes that move results**

| What changed | Before | Now | Who it affects most |
|---|---|---|---|
| Cash the year does not need | Salary, a pension or an RMD beyond the year's spending and tax simply vanished | Saved to the taxable account (at full basis) | Anyone still working, and anyone whose RMDs exceed spending. It also removed a bias toward converting heavily: the conversion tax came out of cash that was about to vanish anyway. |
| Age-65 standard deduction | Missing; the senior bonus was phased out on the couple's combined amount | $1,650 per spouse ($2,050 single) in 2026 on top of the standard deduction; the $6,000 senior bonus phased out per person | Everyone 65 or older |
| Spousal Social Security | The larger of own benefit or reduced half of the spouse's PIA | Own benefit plus the reduced *excess* (SSA dual entitlement) | Couples with unequal records, especially an early claim |
| Survivor Social Security | Applied for one year after a death, then overwritten | Kept for the rest of the plan | Every first-death what-if |
| Income ownership | Every income source treated as joint | A salary or pension stops with its owner's death | First-death what-ifs |
| RMDs | One RMD on the household total, at your age | Each spouse's own IRA at their own age and SECURE 2.0 start age | Couples where the spouse owns an IRA, especially an older spouse |
| Ages | Completed age on the day you ran the plan | The age reached during each tax year | Anyone whose birthday falls later in the year than the run |
| Interest income | Left out of the first year | Counted every year | Plans with interest income |
| Medicare surcharge (IRMAA) | Zero under *Ignore*; charged only while you were on Medicare | Always charged, per person on Medicare; *Strict* and *Avoid* judge the year as simulated | *Ignore* plans; spouses who reach 65 first |
| Bracket rules under a dollar cap | "Fill 22% every year" could convert nothing when a cap made it equal another rule | Converts the capped amount | Plans with a Max Roth Conversion per Year |
| Monte Carlo scenarios | Replayed the planned conversion even in a bad market, booking a shortfall the plan would never cause | A year converts only what it can spare | Plans that are tight on cash |
| Taxable account at a loss | Refused | Accepted; sales from it realize no gain | Holdings below cost |

On the project's standard test household (62/62 couple, $2.5M traditional,
$90k spending) the recommendation moved from *Fill the 22% bracket every year*,
too close to distinguish from three other plans, with this year's conversion
anywhere from $208,200 to $502,550, to **Fill the 12% bracket every year**,
clearly ahead of every finalist, converting **$98,450** this year.

**Changes to what you see**

- A **forced strategy** (the results table's former *Run this policy*) is now scored on every requested
  market scenario, and the success margin is computed from the count each
  strategy was actually scored on.
- The **sale planner** sells losses first, then the smallest gain per dollar
  raised (it used to compare basis per share across different holdings), and
  exported sale plans are dated by your portfolio upload, with any shortfall
  and warnings shown.
- The **What-if page** waits for a plan's settings to load before comparing,
  lists each side's own available strategies, and lets you clear a spending
  floor.
- **Impossible inputs** are refused instead of saved, and **deleting a plan**
  removes it completely or not at all.
- **Tooltips and this guide** no longer claim things the engine does not do —
  pension and IRA exemptions in state tax, partial credit for a target estate,
  a median-return results table.

### The candidate strategies

Every candidate is a **rule** applied year by year over the whole horizon, so
its name says what it does in every year, not only the first:

| Strategy | What it does |
|---|---|
| **No conversions** (`none`) | Never convert. Always a candidate and always scored on every market scenario, so "do nothing" must be *beaten*, never assumed; it is also the baseline the rationale and BETR compare against. |
| **Fill the 10 / 12 / 22 / 24 / 32% bracket every year** (`fill_10_annual` … `fill_32_annual`) | Each year, convert exactly enough to bring taxable **ordinary** income to the top of that bracket, until the Traditional balance runs out or the window closes. Qualified dividends and long-term gains stack above ordinary income on their own rate schedule, so they do not use up the bracket — though pushing them out of the 0% capital-gains zone is a real cost the score counts. In years where converting makes more Social Security taxable, or phases out the senior deduction, the amount is solved against the year as actually simulated. |
| **Convert up to $X annually** (`level_5pct_annual` …) | One fixed dollar amount each year — 5%, 10% or 20% of the Traditional balance when the plan starts, computed once, not recalculated on the remaining balance — until the balance runs out. With a $1,000,000 starting balance the three amounts are $50,000, $100,000 and $200,000, and the results name the strategy that way (*Convert up to $50,000 annually through 2029*; runs saved before October 2026 show the percentage). It can sit between two brackets where no fill rule lands. The amount is a maximum: a cap, the year's spending or the Medicare surcharge setting can make it less or skip a year, so the results state the years each recommendation actually converts in (*converted in 2026–2027 and 2029*). |
| **… through YYYY** (`fill_12_thru_2031`, `level_10pct_thru_2029`, …) | The same rule, applied through a given year and then stopped. Every stopping year the rule could use is a candidate, so the search also chooses *when to stop*. |

On the standard test household that is 95 strategies. Conversions are only
made inside your configured **conversion window** (anytime / before Medicare /
before RMDs / before Social Security) and are filtered by your IRMAA policy, Max
ordinary-income bracket, and Max Roth Conversion / Year. Every strategy gets the
full lifetime simulation and is scored on the first slice of market scenarios; the
leaders, and *No conversions*, are carried to the full set, and the
recommendation is the one with the highest modeled score.

**Older runs.** Until October 2026 the search also built *greedy* strategies,
named after their first-year action — `fill_24`, `level_100`, `defer_1yr`,
`fill_irmaa_tier`, `max_pre_rmd` — that re-chose each later year's amount over
a five-year window. They were removed once the level-dollar rules matched their
results (see [Optimizer internals](OPTIMIZER_HISTORY.md#the-october-2026-gate-that-removed-greedy-rollouts-16-october-2026)).
Runs saved before then still show them, tagged *(greedy)*; their names describe
the first year only.

### The claim-age search

When at least one claim age is searched, the optimizer chooses the claim ages
and the conversion strategy together:

1. **Every claim-age pair** the eligibility rules allow (see [Claim-age
   choice](#claim-age-choice)) gets its own full strategy search on the
   steady-return projection.
2. **Initial comparison.** Each pair's three best strategies, plus *No
   conversions*, are scored on the first 50 market scenarios. Your entered ages get every strategy, so
   *Recommended strategy compared with your original choices* is measured against the same breadth a fixed-age run
   uses.
3. **Finalists.** The five best candidates are then tested using all 300
   market scenarios — the first 50 are among them, so every comparison stays
   paired — along with
   your entered ages' strategies and *No conversions* at the leading ages.
4. **The recommendation** is the fully scored candidate with the highest
   modeled score. A pair tested only on the first 50 cannot win: 50 scenarios
   are not enough evidence to overturn the finalists.
5. **Lifespan checks** re-score the top three as described in [What if you
   live longer or shorter?](#what-if-you-live-longer-or-shorter). They are
   reported, never used to rank.

A couple who can each claim at 63–70 has 64 pairs; the whole search takes a few
minutes. The results' **Explore other Social Security claim ages** grid shows step 2; Close
alternatives and the comparison with your original choices show steps 3–4.

### IRMAA tiers

**IRMAA** (Income-Related Monthly Adjustment Amount) is a Medicare surcharge. Once your **MAGI** (modified adjusted gross income) crosses a threshold, your Part B and Part D premiums step up for the whole year — and because Medicare looks at your MAGI from **two years earlier**, a big conversion today can raise your premiums two years later. The thresholds are **cliffs**: one dollar over and the entire tier's surcharge applies, so they're worth planning around.

**Restrict conversions at Medicare surcharge thresholds** keeps each conversion *just below* the next threshold above your income; **Allow conversions to cross** lets a conversion cross one when the tax it saves is worth more. (Older runs may also show the retired greedy strategy *Fill to next IRMAA tier*, `fill_irmaa_tier`, which converted up to that threshold.) The thresholds are indexed each year; the **2026** figures are:

| Your MAGI is at or below… (Single) | …or (Married Filing Jointly) | Extra Medicare premium vs. standard (per person / year) |
|---|---|---|
| $109,000 | $218,000 | $0 (standard) |
| $137,000 | $274,000 | ≈ $1,148 |
| $171,000 | $342,000 | ≈ $2,885 |
| $205,000 | $410,000 | ≈ $4,620 |
| $500,000 | $750,000 | ≈ $6,355 |
| above $500,000 | above $750,000 | ≈ $6,936 |

The surcharge is **per person on Medicare**, so a couple pays roughly double. (Example: a joint MAGI of $278,000 sits in the third row — about $2,885 each, ≈ $5,770/yr for the couple.) The exact premiums live in `backend/src/data/tax_rules/irmaa.py`, each year citing its CMS notice.

> **Sized against the year as simulated.** The **Strict / Avoid** policies judge a conversion by the year's income *after*
> its spending withdrawals: if you fund spending by **selling taxable assets**,
> the conversion's tax is paid by selling more, which realizes more gains, so
> income rises by more than the conversion itself. Until October 2026 Avoid
> added the conversion to the income before those sales, and a conversion it
> let through could land above the tier. Verify the year's MAGI against the
> exported Tax Audit sheet if a surcharge matters to you.
>
> The bracket-fill rules work the same way: a `fill_*` conversion is sized
> against the year as actually simulated — including the gains your spending
> withdrawals realize, and the extra Social Security those gains make taxable —
> so it lands on the bracket's top rather than sailing past it. That includes
> spending drawn from the traditional IRA once the taxable account is empty:
> that withdrawal is ordinary income too, and until October 2026 the bracket
> fills and the **Max ordinary-income bracket** cap both ignored it, so in those
> years a "12% fill" could land in the 24% bracket. If you have runs from before
> then whose spending comes out of the IRA during conversion years, re-run them.
> Note that the year table's *Marginal %* is the rate on the **next** dollar, so a
> correct `fill_12` year shows 22% there; check *Bracket Room* instead, which
> reads "$0 left in 12%". A fill year whose Bracket Room names a higher bracket
> than the rule's is a bug; please report it.

**Why the Traditional balance can survive to the end.** A rule stops when its
bracket is full, its stop year passes, or the conversion window closes — and RMDs
and spending withdrawals compete for the same bracket room. A *Fill the 12%
bracket through 2031* plan deliberately leaves the rest of the IRA to RMDs; the
year table's rationale says which reason applies in each year without a
conversion.

Each conversion year also reports its **BETR** (break-even tax rate, per Vanguard's July 2025 methodology): the future marginal rate at which that conversion would break even, compared against your projected future rate. BETR is the *diagnostic*; the lifetime objective above is what actually *decides*.

**Everything except the strategy is held identical** when strategies are
compared. Each uses the same household, spending, conversion window, IRMAA
policy and the same market scenarios as the recommendation — and, outside a
claim-age search, the same claim ages — so the differences isolate the effect
of the strategy (and, in a search, of the claim ages beside it). This also means
your conversion window gates *every* candidate: with a *Before Social Security*
window, every strategy stops converting once benefits start.

**A worked example** of reading the alternatives (measured September 2026 under the retired *Lifetime taxes* priority, before the October corrections — the figures would differ today, the reading does not). A couple (63 and 59, $150k/yr spending, ~$125k/yr of dividends) ran with Optimization Priority = *Lifetime taxes*. The recommendation was the greedy *Fill the 24% bracket*, and the alternatives showed:

| Strategy | Lifetime taxes Δ | Estate (heir-adj.) Δ | Success Δ |
|---|---|---|---|
| Level: ½ of IRA over lookahead (greedy) | +216,658 | +300,748 | +7.0% |
| Level: ¼ of IRA over lookahead (greedy) | +206,420 | +344,344 | +6.0% |
| Fill the 12% bracket (greedy) | +199,687 | +373,388 | +7.0% |

Every alternative pays **more** lifetime tax (positive Δ) — that is *why* Fill-the-24% won under a taxes-only priority. But every alternative also leaves **more** estate and funds spending in **more** paths: converting hard minimizes lifetime tax by paying a big bill early, which drains the portfolio's buffer. The table quantifies the trade that priority made — here, roughly $200k of extra lifetime tax would buy ~$340–370k more heir-adjusted estate and 7 points of robustness. That trade is exactly why the priority was retired: the optimizer now maximizes the after-tax estate, so it takes the extra estate.

A strategy can also pay *less* lifetime tax and still lose: prepaid conversion taxes forfeit years of compounding, and the objective counts that.

### Older forced-strategy runs

Until October 2026 each row of the alternatives table had a **Run this policy**
button, which re-ran the plan with that strategy pinned. The button is gone —
the results page is for reading, and a what-if belongs on the What-if page —
but runs made with it still open normally. Their banner reads **Strategy you
chose to run** instead of *Recommended strategy*, a *Forced-policy run* notice
names the optimizer's own pick for those inputs and links **View the optimized
run →**, and in Close alternatives the optimizer's pick is tagged *optimizer's
pick*. The Excel Results sheet and the PDF summary say the same.

**Dashboard → View results opens the plan's latest optimized run**, not a newer
forced one: a forced run is a what-if, not the plan's answer. If every run of
the plan was forced, it opens the newest.

### Trying a variant of the inputs (e.g., a different conversion window)

Close alternatives only varies the *strategy* (and, in a claim-age search, the claim ages). To vary an *input* — say, conversion window *Anytime* instead of *Before Social Security* — with everything else unchanged:

1. **What-if page** (fastest): choose the plan, leave **Baseline** at the saved values, change only the Conversion Window under **Your changes**, and click **Compare**. You get the exact difference the input makes. Force the same Strategy on both sides (under Advanced options) to isolate the input's effect from the optimizer changing its pick.
2. **New plan via copy** (durable): on the wizard's *Start your new plan* screen choose **Copy this plan's inputs**, change the one input, and run. This creates a separate plan with full results, exports, and run history — What-if results are not saved as runs.

### Spending is after-tax (grossed-up withdrawals)

The annual spending you enter is treated as **after-tax spending money**. Each simulated year, the engine iterates withdrawals and taxes to a fixed point: withdrawing more triggers more tax, which requires withdrawing more, until net cash after *all* taxes (federal, state, IRMAA) equals your spending target to within $1. You can verify it in any exported row: `income + withdrawals − total tax = required spending`, to the penny.

**A conversion never takes money the year needs to live on.** Money you convert lands in the Roth, but the year's spending can only draw on the Roth balance you started the year with. So if a candidate conversion would leave the year short — typically a small IRA with no taxable account behind it — the tool cuts the conversion back to the most the year can spare, or drops it below $1,000. Before October 2026 such a conversion went ahead and the year reported a shortfall while the converted money sat in the Roth: a plan nobody could follow. The same rule holds in every Monte Carlo scenario: if a market fall leaves a year unable to afford its planned conversion, that year converts only what it can spare. (Until October 2026 the scenarios replayed the planned amount regardless, so a bad market could show up as a spending shortfall the plan would never actually have caused.)

### A worked example: why "no conversion" can win

A real scenario from testing (September 2026) — married couple, 63 and 59, $150k/yr spending, $1M taxable account paying **$125k/yr in dividends** ($45k qualified), $636k traditional, Social Security starting at 67:

Their ordinary-income marginal rate before SS is only **12%** — which looks like cheap conversion headroom. But their qualified dividends and realized capital gains sit in the **0% capital-gains zone**, and conversion income stacks *underneath* capital gains on the tax ladder. Each conversion dollar therefore costs:

> 12% (ordinary tax on the conversion) **+ 15%** (a dividend/gain dollar pushed out of the 0% zone) ≈ **27% effective**

Their projected future marginal rate — once SS and RMDs arrive — is about **22%**. Converting at an effective 27% to avoid a future 22% loses money, so the optimizer picks *No conversions*. The Alternative Policies table showed *Fill the 22% bracket* would cut lifetime taxes by $211k yet still end **$237k behind** on heir-adjusted estate — the early tax payment and its lost compounding outweighed the savings.

The general lesson: bracket numbers alone don't decide conversions. Capital-gains stacking, IRMAA surcharges, heir tax rates, and the *timing* of tax payments all enter the score — which is why the optimizer simulates everything rather than following a rule of thumb.

---

## The What-if Page

The What-if page runs one plan through the optimizer twice — **Baseline**, your plan as saved, and **Your changes** — and reports how they differ in lifetime taxes, terminal estate, the share of scenarios with spending funded, and the tax break-even year. Both runs share the same market paths, so any difference you see comes from your changes, not random variation. Choose the plan by its nickname at the top.

Both sides start prefilled with the plan's saved values — settings *and* constraints. **Compare** stays off until they have loaded for the plan you picked (and says so, with a Retry, if they can't be), since comparing on half-loaded forms would quietly run the wrong plan's settings; switching plans clears the previous result. Every field you change is tinted and marked *changed*, and a line above the Compare button lists the changes — *Comparing: Annual spending $150,000 → $120,000*. Change one setting to ask a question:

- **Annual Spending** — "can I afford $160k instead of $150k?" Higher spending forces larger (more heavily taxed) withdrawals and shrinks the estate.
- **Claim Age** (yours and your spouse's, shown when Social Security is configured) — "claim at 62, 67, or 70?" Each side holds its claim ages fixed; the benefit adjusts for early or late claiming and starts in the year each person reaches the chosen age. To have the optimizer choose claim ages, run a claim-age search from the wizard. A plan saved with a searched age and no comparison age starts here at the ages its latest run recommended.
- **Model first death at age** (shown when both spouses have Social Security) — *"how much more should we convert if one of us dies at 78?"* See [The widow's penalty](#the-widows-penalty) below.
- **If markets go badly / Minimum annual spending** — *"what if we held spending rigid instead?"* Prefilled from the plan so you can see which rule it uses. Emptying the minimum removes it for that scenario.
- **Skip market simulation** (a checkbox beside the Compare button, applying to both sides) — see [The deterministic baseline](#the-deterministic-baseline) below.
- **Advanced options** (collapsed; its summary counts any changes inside it):
  - **Strategy** — force a specific conversion strategy (e.g., *Fill the 22% bracket every year* vs. *No conversions*) instead of letting the optimizer choose. Each side's list holds the strategies **that side's** settings allow — closing the conversion window or adding a cap removes some — and a choice that stops being available is flagged.
  - **Medicare surcharge thresholds / Conversion Window / Max ordinary-income bracket / Max Roth conversion per year** — the constraint settings. Fixed-amount strategies are listed by dollar amount, smallest first. A custom amount and duration (say, exactly $75,000 a year for four years) is not offered: the strategies are the ones the optimizer generates.

Below the cards and chart, a **Year by Year** table lists both scenarios side by
side — conversions, taxes and total balance per year. It opens on the years in
which either plan converts, with *Show all years* for the full horizon. Read the
rows, not just the totals: two strategies can reach nearly the same lifetime
conversion on opposite schedules (one front-loading at 24% while the other waits
for the 10–12% years), and the summary cards cannot show that.

The result header names each side's recommended strategy (marked *(forced)* when you chose it), so you always know what plan produced each column of numbers. Below it, the difference cards say in words which side comes out ahead — *"Your changes: $125,643 less tax"*, *"Baseline: $252,200 larger estate"* — or *"Same in both"*. Lifetime taxes there are nominal totals. A chart overlays the two sides' total portfolio balances.

### The deterministic baseline

Tick **Skip market simulation** and every year grows at exactly your Expected
Return — no randomness, no sequence-of-returns, no averaging. This is the
interpretable comparison: *what do these strategies do if markets behave as
assumed?*

Pair it with the **Strategy** option (under Advanced options) to line the bracket
rules up against each other. All five bracket-fill rules are available as consistent "every year"
strategies:

| scenario | conversions | taxes (nominal) | taxes (PV) | estate |
|---|---|---|---|---|
| No conversions | $0 | $1,276,963 | $922,668 | $2,231,163 |
| Fill 10% every year | $184,250 | $1,094,011 | $837,974 | $2,213,946 |
| Fill 12% every year | $564,438 | $866,437 | $747,246 | $2,007,969 |
| Fill 22% every year | $1,063,249 | $754,329 | $704,849 | $1,796,184 |
| Fill 24% every year | $1,084,716 | $680,830 | **$658,335** | $1,820,362 |
| Fill 32% every year | $1,052,978 | **$679,302** | $664,145 | $1,736,293 |

*(Couple aged 62 and 61, California, plan to 87. $1M taxable with zero cost
basis, $1M traditional, $500k Roth. $150k spending, 6% return, 3% inflation.
Salary $100k through 2028 and $50k through 2027; $10k ordinary and $2k
qualified dividends. Social Security PIA $5,000/mo claimed at 69 and $1,500/mo
at 67. Optimization Priority = Lifetime taxes (since retired), IRMAA policy =
Soft, no bracket cap — a cap would remove the higher rules from the field
entirely. Measured 15 October 2026, before Social Security COLA and projected
tax tables; the figures will be re-measured.)*

Read the last two rows carefully before copying them. Filling the 24% or 32%
bracket every year does minimize **lifetime tax** here (32% in nominal dollars,
24% in today's dollars), which is what this household's priority asked for —
but each converts over a million dollars and ends with a **smaller** estate
than filling 12%. That is the priority doing
exactly what it was set to do, not a free lunch.

**What the simulation was and was not doing.** Worth knowing before you decide
how much the checkbox changes:

- Monte Carlo varies **only the annual return** — one independent draw per year
  from a bell curve centred on your Expected Return. Your **inflation rate is
  never varied**, nor is spending, Social Security, or anything else.
- The **taxes, estate and conversion figures were already deterministic**. They
  come from the steady-return projection, both before and after you tick the
  box. Only two things change: the **ranking** (which strategy is recommended),
  and the **share of scenarios with spending funded**.
- With the simulation off, the share of scenarios with spending funded is 100% or 0%
  and carries no information, so the page hides that card rather than showing
  a difference of two certainties.

Use the deterministic view to understand *what a strategy does*, then turn the
simulation back on to ask *how well it holds up when markets misbehave*.

### The widow's penalty

This is the one what-if that answers a question your plan of record structurally
cannot, and it is worth running once even if you never look at it again.

When the first spouse dies, the survivor files **single** — roughly half the
bracket widths and half the standard deduction — while keeping the larger
Social Security benefit, losing the smaller, and continuing to take the **full**
RMDs from a portfolio that did not shrink. That combination is frequently the
highest-tax stretch of a couple's retirement, and it is exactly what Roth
conversions hedge against.

Income stops with the person who earned it: a salary or pension entered as the
deceased's own ends at the death, and only joint income continues, so enter a
pension with a survivor option as joint. (Until October 2026 every income
source was treated as joint here, whatever owner you chose.)

Your plan of record cannot see it, because it assumes you both live to your
Plan-to ages. So set the death age under **Your changes** and compare:

| | Baseline: both alive | Your changes: spouse dies at 78 |
|---|---|---|
| Recommended strategy | Fill the 12% bracket every year | **Fill the 24% bracket** (greedy) |
| Recommended conversions | $453,771 | **$699,480** |
| Projected future marginal rate | 24% | **35%** |
| Lifetime taxes (nominal) | $783,308 | **$587,538** |

*(Couple born March 1963 and June 1965 — 63 and 61 in 2026 — in California,
planning 30 years. $500k taxable with $350k basis, $1.8M traditional and $200k
Roth; $130k spending; Social Security PIAs $4,000 and $2,400 a month, both
claimed at 67. 300 market scenarios. Measured 15 October 2026.)*

The projected-rate row is the mechanism. That rate feeds every break-even verdict in
the rationale panels: at 24% the optimizer declines conversions costing 24% or
more, at 35% those same conversions are clearly worth doing. Here it moves the
recommendation by **$246,000**, and lifetime tax comes out *lower* in B despite
the harsher single-filer years, because converting ahead of them is what
avoids the penalty. (Measured before the greedy strategies were retired; the
lesson, not the strategy name, is the point.)

**Why you cannot just re-run the plan after a death instead.** You can, and you
should — a survivor's plan works correctly on its own. But conversion windows
are time-limited and non-recoverable. The low-bracket stretch between retiring
and RMDs is about eight years; if you under-convert through it because the model
showed 24%, re-planning afterwards cannot get those years back.

**What it does not claim.** Choosing a death age is a guess, and the tool will
not make it for you — that is precisely why this lives here rather than in the
wizard. Treat it as a sensitivity test: if converting more looks right at 75,
80 *and* 85, that is a robust signal. Also note the direction depends on the
survivor's spending — a survivor whose spending stays flat may convert *less*,
because larger withdrawals eat the bracket headroom conversions would have used.

Two related simplifications remain: pension **survivorship elections** are not
modelled (a pension that continues to a survivor should be entered as *joint*;
one that stops should be owned by the person receiving it), and mortality is
never sampled — the Monte Carlo varies investment returns only.

Note: comparisons are exploratory and are **not saved as runs**. When a what-if deserves a permanent record, create a copied plan with that input changed (see [Trying a variant of the inputs](#trying-a-variant-of-the-inputs-eg-a-different-conversion-window)).

---

## The Portfolio Sale Planner

The Portfolio Sale Planner turns a plan year's "withdraw $X from taxable" into "sell *these* positions." It works from aggregate positions with average cost basis — the same resolution the simulation itself uses — so ballpark accuracy is by design, and preparing the file takes minutes, not an afternoon of lot exports.

**Where it lives.** Your portfolio is **app-level, not per plan** — it describes your real holdings, which don't change between what-if scenarios. Manage it from the top-nav **Portfolio** tab: click **Upload file** to pick a CSV or tab-separated file (or expand *…or paste instead*), and the stored positions are listed below with a total and the upload date. Every plan and run reuses this one portfolio, so you only refresh it episodically — when prices have drifted or you've actually bought or sold. The Portfolio tab is **holdings only** — you no longer enter a "target cash" amount there; sale planning happens on the results page (below).

### The CSV template

One row per position (download the template from the Portfolio tab):

```csv
symbol,shares,price,cost_basis,account_type,long_term
VTI,500,285.10,95225,taxable,
AAPL,200,240.00,19040,taxable,
SNOW,100,180.00,21000,taxable,no
VTSAX,1000,132.50,,traditional,
```

- `cost_basis` is the **total** dollars you paid for the whole position — the same aggregate figure you entered on the Accounts screen, not a per-share number. The planner derives per-share basis internally by dividing by `shares`, which is both less work for you and more precise (no per-share rounding).
- `account_type` is `taxable` / `traditional` / `roth`. `cost_basis` is required for taxable rows and ignored elsewhere (basis is irrelevant inside IRAs).
- `long_term` is optional: blank means yes. Mark positions bought **within the past year** with `no` — their gains would be taxed at ordinary income rates, so the planner sells them last and warns if it must touch them. For long-accumulated retirement positions, "everything is long-term" is almost always correct.
- Dollar signs and commas in numbers are fine; the parser strips them.
- You can paste **tab-separated** data too — copying a range straight out of Excel or Google Sheets works as-is. Header names are matched loosely, so `Cost Basis` (with a space) is read the same as `cost_basis`.

**Where the numbers come from:** your brokerage's one-click positions download already has them — Fidelity, Schwab, and Vanguard all report a **Cost Basis** (total) column for each holding alongside shares and current price. Copy those columns into the template as-is; no per-share division needed.

**Upload fresh prices.** Prices change daily, and the sell lists (on the results page and in the exports) are priced from whatever you last uploaded. A neat workflow: keep a spreadsheet whose price column is `=GOOGLEFINANCE(A2,"price")` (near-live quotes), then save as CSV and upload — your shares and basis rarely change, so only the formula column stays live.

### Getting a sale plan (on the results page)

Sale planning happens **in context on the results page**, not on the Portfolio tab. Expand any year with a taxable withdrawal and click **"Plan this sale"** — the sell list appears **right there**, no navigation. In a **Roth conversion year**, the row also shows the purpose split: how much of the withdrawal funds spending vs. the conversion's tax bill (the engine's gross-up already sized the withdrawal to cover both). If you haven't uploaded a portfolio yet, the row links you to the Portfolio tab.

The plan sells in tax-priority order:

1. **Positions at a loss** first, long-term then short-term (harvesting the loss offsets other gains — especially valuable in a conversion year),
2. then **long-term gains**, smallest gain per dollar raised first — across different holdings, not highest basis per share, which compares nothing when share prices differ,
3. then **short-term gains** last, with a warning.

(Until October 2026 gains were ranked by basis per share across all holdings, which could sell a $1,000 share carrying $500 of gain when ten $100 shares would have raised the same cash with $100; and short-term losses came after long-term gains.)

Each row shows dollars to sell, approximate shares, and the realized gain or loss. Remember the resolution: with average basis, this is position-level guidance to the nearest thousand dollars, not broker-ready lot instructions — exactly the fidelity the plan itself runs at.

### Sale plans in the exports

When a portfolio is uploaded, the run's **CSV, Excel, and PDF exports** each include a **Sale Plan** section (a sheet in Excel, a page in the PDF, a trailing block in the CSV) with the sell list for the **first** taxable-withdrawal year only — the one you act on before re-running next year. It's stamped **"prices as of &lt;date&gt;"** with the date you **uploaded** the portfolio (and the date the file was generated), so a stale upload is visible. If your holdings can't raise the whole withdrawal it says how much was raised and how much is **short**, and it carries the planner's warnings (short-term sales, holdings without a date). Re-download after prices move or your holdings change. (Until October 2026 the stamp was the download date whatever the prices' age, and the shortfall and warnings were left out.)

---

## Exports: CSV, Excel, and PDF

All three exports are available from the Results page, and every run automatically saves all three to the `reports/` folder as a permanent record. Each file is stamped with its **Run ID** and **Household ID** (a leading comment in the CSV, the top of the Results and Inputs sheets in Excel, the title page in the PDF), so a saved report is always traceable to the run that produced it.

**CSV** — a spreadsheet-compatible file with all per-year projection data (balances, taxes, conversions, income by type). Open in any spreadsheet program.

**Excel** — a multi-sheet workbook that opens on **Results** (the run and plan IDs, the recommended strategy, the summary figures with the same labels and hint lines as the page — *No market simulation* on a run without one — every advisory, and **How we simulate market outcomes** with the run's recorded assumptions), then, for a claim-age search, **Claim-age search** (below), **Inputs** (the exact snapshot that produced the run), **Yearly Plan** (the full table with per-year narratives), **Alternatives** (Close alternatives as the page ranks them: strategy, claim ages, average modeled score, difference from the recommendation, scenarios with spending funded, comparison result and *Roth conversion in 2026*, then the tax and estate differences headed *assuming a steady 6% return*; the close-call sentence sits above the table), **Tax Audit** (the per-year worksheet-line derivation — see [Verifying the numbers](#verifying-the-numbers)), **Charts** (native Excel charts of balances, taxes, and conversions), and — when a portfolio is uploaded — **Sale Plans** (per-year sell lists; see [the Sale Planner](#sale-plans-in-the-exports)).

**PDF** — a formatted report including the inputs snapshot, a summary that names the strategy (*Recommended strategy*, or *Strategy you chose to run* on an older forced run), the market explanation, charts (labelled as the steady-return projection), Close alternatives (the score-ranked table, then *Compare taxes and estate assuming a steady 6% return*), the claim-age search tables for a search, the full year-by-year table, a narratives appendix, and (when a portfolio is uploaded) a **Sale Plans** section. Opens in a browser tab; suitable for printing or sharing with an advisor.

Both the CSV and the reports carry the per-year **Sale Plans** section only when you've uploaded a portfolio, each stamped with the price date.

**Why the buttons behave differently.** The CSV and Excel buttons trigger a browser *download* (they're not viewable in a browser tab), while the PDF *opens* in a new tab. That's normal browser behavior for those file types — nothing is wrong. The buttons always regenerate a fresh copy from the stored run; the copies already sitting in your `reports/` folder are identical.

**The PDF's two "narrative" parts are different things.** The always-present **Narratives Appendix** is the built-in per-year rationale (the same text shown on the Results page). The optional **Advisor Commentary** at the front is the *LLM-written* summary — it appears **only if you clicked "Generate AI Summary" before downloading** (see [AI Summary](#ai-summary-optional)). If your local-LLM commentary isn't in the PDF, generate it first, then re-download.

**The claim-age search in the exports.** A search adds the same tables to all three formats, under *Explore other Social Security claim ages* — a *Claim-age search* sheet in Excel, a section in the PDF, a trailing block in the CSV: the claim-age pairs from the initial comparison (each column naming its scenario count), the strategies tested using all the market scenarios, *Recommended strategy compared with your original choices* (noting when no comparison claim ages were provided), *What if you live longer or shorter?* (one row per strategy, one column per check, and *Highest among the strategies checked?*), any excluded ages with the reason, and the search assumptions. Strategies carry readable names and claim ages (*You 70 · Spouse 69*) rather than internal keys, and comparisons use the page's four labels. A run saved before the recommendation's initial-comparison score was stored leaves that comparison blank and says it is unavailable.

**Saved runs keep their stored text.** The exports print each year's narrative as it was saved; the results page restates older runs' vaguer no-conversion sentence (see [Rationale Panel](#rationale-panel)), but the files do not.

In all exports, a person's age column goes blank once past their own Plan-to age (the projection continues to the longer-lived spouse's horizon).

---

## Verifying the numbers

Every number in a run can be traced. Three layers, from cheapest to most rigorous:

### The built-in identities

- Every year satisfies `income + withdrawals − total tax = required spending` — check it in any exported row.
- The project's tests check the tool's promises on **hundreds of randomly generated households**, not just a few hand-built ones: a "fill NN%" conversion never lands above that bracket, nothing the bracket cap allows lands above it, every year funds its spending unless the accounts are empty, and RMDs start at the right age for your birth year. Two of the October 2026 fixes were found this way.
- Every tax bracket, deduction, and IRMAA tier lives in a plain data file under `backend/src/data/tax_rules/`, each block citing its IRS Revenue Procedure or CMS notice. You can compare any number to the cited primary source without reading code.

### The Tax Audit sheet (Excel export)

The **Tax Audit** sheet shows, for every year, exactly how the tax was derived — one column per year, worksheet line by worksheet line:

- the ordinary-income stack (salary, pension, dividends, the taxable portion of traditional distributions, gross vs **taxable Social Security**),
- preferential income (qualified dividends, realized long-term gains),
- the federal derivation (AGI → deduction, including the extra standard deduction each spouse gets at 65 and the temporary senior bonus → taxable income → tax on ordinary income vs LTCG vs NIIT → federal tax),
- state tax, the **IRMAA look-back MAGI** (two years prior) and surcharge, and total tax.

The identities hold exactly: the ordinary-income lines sum to the total shown, and federal + state + IRMAA equals the year's total tax. To verify a year by hand, take these lines to the 1040 instructions — the *Qualified Dividends and Capital Gain Tax Worksheet* and the *Social Security Benefits Worksheet* — or hand the sheet to a CPA. Quicker but weaker: enter the same numbers into any reputable 1040 calculator and expect agreement within rounding.

### Cross-checking the whole plan externally

For the multi-year trajectory (not just one year's tax), rebuild the household in an independent model — the free Bogleheads *Retiree Portfolio Model* spreadsheet is a good comparator; Pralana and Boldin are strong paid options. Expect **direction and magnitude agreement, not penny agreement**: every planner differs on return sequencing and inflation treatment. Known differences to expect from this tool's documented simplifications: tax tables past the latest published year are projected at your inflation assumption (federal brackets, deductions and IRMAA thresholds; California's brackets; other states stay frozen), Social Security grows by your COLA assumption (your inflation rate unless you set one), and the first two IRMAA years use a MAGI proxy. In the other direction, this tool applies the **spousal Social Security benefit** — a spouse receives their own benefit plus the excess of 50% of the higher earner's PIA over their own PIA (reduced if it starts before full retirement age), from the year the higher earner files — which hand-built spreadsheets commonly omit.

### Reconciling against your own spreadsheet

If you have built your own conversion model, it can be tied out against this
one almost exactly. Most of the work is making the two answer the same
question, because by default they do not.

**Set the app up to match the question your sheet asks.**

1. **Tick "Skip market simulation"** on the [What-if page](#the-deterministic-baseline). This is the single most important step. With the simulation on, the optimizer ranks strategies on their average across 300 return paths *minus the spending they fail to fund* — so for an underfunded plan it can recommend **no conversions at all** where your sheet, growing at a smooth expected return and never running out, shows a large one. That is not a tax disagreement; the two models are scoring different things. See [Monte Carlo scoring and the shortfall charge](#monte-carlo-scoring-and-the-shortfall-charge).
2. **Force the same strategy on both sides** with the Strategy option under Advanced options — normally *Fill the 12% bracket every year* — so you are comparing schedules, not comparing your schedule against whatever the optimizer picked.
3. **Clear the Max ordinary-income bracket cap**, or make sure your sheet applies the identical cap. See the note under [Step 5](#step-5--spending-and-review) for why a low cap can suppress conversions entirely.
4. **Compare like with like.** The tool maximizes the after-tax estate net of unfunded spending; if your sheet minimizes lifetime tax instead, expect it to favour plans with less income.

**Compare taxable ordinary income, not conversion dollars.** This is the line
that should agree, and the one that tells you where a disagreement comes from.
"Fill the 12% bracket" means one thing: after the conversion, taxable ordinary
income sits on the bracket's top — $100,800 married-filing-jointly in TY2026.
Two models can converge on that figure while converting different amounts,
because the conversion is only the *last* item in the ordinary-income stack.
Anything else in that stack — Social Security, a traditional withdrawal, an
RMD — displaces conversion dollar for dollar. Read it off the **Tax Audit**
sheet in the Excel export.

**Where the two will differ, in the order you will hit it.**

| Symptom | Usual cause |
|---|---|
| App converts **nothing** | The simulation was left on, or the bracket cap forbids it. Start at steps 1 and 3 above. |
| Conversions differ from the year Social Security starts | Your sheet may omit the **spousal benefit** (50% of the higher earner's PIA). Up to 85% of the difference is taxable ordinary income, and it displaces conversion one-for-one. |
| Conversions differ in late years only | The app **solves** withdrawals to fund your spending target inflated each year; a calculator sheet takes withdrawals as typed input. Once the taxable account is exhausted the app must draw from the traditional IRA, which is ordinary income and eats bracket room before any conversion. Compare the funded-spending line first. |
| Your sheet shows lower tax on the same income | Check it computes **NIIT** (3.8% above $250k MAGI joint, not inflation-indexed, so it appears exactly when conversions push you over) and charges **IRMAA per person on Medicare**, not per household. |
| Small, drifting differences from 2027 onward | Tax tables past the latest published year are projected here at your inflation assumption, and Social Security grows by your COLA. If your sheet freezes either, the gap widens with time. Set the COLA to 0 to match a sheet with flat benefits. |

Worked through on a real household, those account for the difference to within
a dollar a year. If something remains unexplained after all of them, it is
worth reporting.

---

## Your data stays on your machine

This application runs entirely on your local computer. No plan data, portfolio positions, or personal details are transmitted to any external server unless you explicitly configure an AI summary (see below).

**What never leaves your machine:**
- Your plan inputs (ages, balances, income, spending)
- Portfolio positions, tickers, shares, and cost basis uploaded to the Portfolio Sale Planner
- All optimization results, tax projections, and exported reports
- The local DuckDB database (`data/retire.db`) where runs are stored

**If you configure an AI summary with an Anthropic API key**, a narrow, privacy-scoped payload is sent to Anthropic's API when you click "Generate AI Summary." That payload contains:

- Filing status, required spending, and SS claim ages
- The recommended strategy's totals (lifetime taxes, terminal estate, share of scenarios with spending funded, total conversions)
- The year-by-year table of tax and balance figures
- Optimizer warnings and the close alternatives' differences

It does **not** contain your name, birth dates, state, account balances by institution, or any portfolio positions. The AI never sees what you uploaded to the Portfolio Sale Planner.

**The AI Summary is entirely optional.** If you do not configure an API key or local LLM, the button does not appear and nothing ever leaves your machine. For complete privacy while still getting AI commentary, use a local LLM instead (see [AI Summary](#ai-summary-optional) below).

### Starting over (resetting your data)

Because everything lives in one local file, wiping your data is a single command. Two maintenance scripts in `scripts/` do this — **stop the backend first** (the database allows one writer at a time, so a running server blocks the script), then run one of:

- `python scripts/db_purge.py` — deletes every row (plans, runs, and your uploaded portfolio) but keeps the table structure.
- `python scripts/db_reset.py` — drops and recreates the database from scratch.

Both ask you to type `YES` to confirm (add `--yes` to skip the prompt), and both operate on `data/retire.db` by default. **Restart the backend afterward** — on startup it re-creates the single default profile the Portfolio tab needs. You'll then re-enter your plans and re-upload your portfolio from a clean slate.

---

## AI Summary (optional)

When an LLM is configured, a **"Generate AI Summary"** button appears on the Results page. Clicking it sends the run's figures (the recommended strategy's totals, the year-by-year table, the close alternatives' differences, the input summary, and warnings — no birth dates or personal identifiers) to the model, which writes a plain-English commentary. The text is **stored with the run** and appears as an **"Advisor Commentary"** section at the front of the PDF report on your next download — generate once, reuse everywhere.

Two ways to configure it (set either in a `.env` file at the project root; copy `.env.example`):

**Anthropic API:**
1. An API key from [console.anthropic.com](https://console.anthropic.com/).
2. `pip install -e ".[llm]"`.
3. `ANTHROPIC_API_KEY=your_key` in `.env`.

**A local LLM (fully private — nothing leaves your machine):** any OpenAI-compatible server works (llama.cpp `llama-server`, LM Studio, Ollama, vLLM). No extra package needed:

```
LLM_BASE_URL=http://localhost:8080/v1
LLM_API_KEY=local
LLM_MODEL=your-model-name
```

When `LLM_BASE_URL` is set it takes precedence over the Anthropic key.

If the model cannot be reached or returns an error, the button reports it — for a local server, *"The LLM request failed: Could not reach the LLM at http://localhost:8080/v1 …"*. That almost always means the server is not running or `LLM_BASE_URL` is wrong. (The local client's one dependency, `httpx`, is part of the normal install; if you installed before October 2026, run `pip install -e .` once.)

**Customizing the voice:** set `LLM_SYSTEM_PROMPT_FILE=docs/prompts/advisor.md` (or your own file) to replace the built-in prompt. The shipped `advisor.md` produces a formal advisor-style commentary — executive summary, the highest-impact decisions, risks, and what to revisit annually. Whatever persona you write, keep its two safety rules: the model must use only the numbers provided (the tables are ground truth; the LLM is commentary) and must not give investment advice. Small local models write fluent prose but cannot be trusted to do arithmetic — the prompt design is what keeps them honest.

The AI summary is an educational aid. It does not constitute tax or financial advice.

---

## Keeping tax data current

Tax rules change every year. This section explains how to update the data files when the IRS publishes new numbers — no programming experience is required.

### Overview

All tax parameters live in plain text files under `backend/src/data/tax_rules/`:

| File | Contains |
|------|---------|
| `federal.py` | Federal income tax brackets, standard deductions, LTCG thresholds (one block per year) |
| `irmaa.py` | Medicare Part B and Part D premium tiers (one block per year) |
| `state_brackets_<YEAR>.csv` | State income tax brackets, one CSV per year (e.g. `state_brackets_2025.csv`); the loader picks the simulated year's file and clamps to the latest available with a logged warning — the same policy as federal |
| `state.py` | Loader for the year-keyed state CSVs + which states tax Social Security |
| `ANNUAL_UPDATE_CHECKLIST.md` | Step-by-step checklist for the full yearly update (federal, IRMAA, and state sections) |

Each block in these files has a comment citing its IRS or CMS source, so you can always verify the numbers.

### When to update

- **October/November** — The IRS publishes next year's tax brackets and the CMS publishes next year's Medicare premiums.
- **After any mid-year tax legislation** — If Congress passes a law that changes rates or thresholds for the current year, update immediately.

### How to update federal brackets (example: adding tax year 2027)

1. Open `backend/src/data/tax_rules/federal.py` in any text editor (Notepad works).

2. Find the block for 2026 (the most recent year). It looks like:
   ```python
   2026: FederalTaxYear(
       year=2026,
       source="Rev. Proc. 2025-32 ...",
       brackets={
           "single": _b(("12400", "0.10"), ...),
           ...
       },
   ),
   ```

3. Copy the entire 2026 block (from `2026:` through the closing `),`).

4. Paste it immediately after the 2026 block, before the closing `}` of the `FEDERAL` dictionary.

5. Change `2026` to `2027` in the pasted block.

6. Update the `source=` line with the actual IRS Revenue Procedure number (e.g. `"Rev. Proc. 2026-45"`).

7. Replace every dollar amount and rate with the values from the IRS Rev. Proc.:
   - **§2.01** — Ordinary income tax brackets (10%, 12%, 22%, 24%, 32%, 35%, 37%)
   - **§2.03** — Long-term capital gains thresholds (0%, 15%, 20%)
   - **§2.09** — Standard deduction amounts

8. Save the file.

9. Open a terminal, go to the project root, and run:
   ```bash
   source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
   pytest
   ```

   If a test fails, it tells you which number disagrees (e.g. "single bracket 3 upper bound mismatch: expected 103350, got 103250"). Passing tests are **not** proof the new figures are right: they check structure and agreement with the existing fixtures, not the statute. Check each figure you typed against the IRS publication itself — a missing or mis-keyed amount can pass every test.

10. You can also run the structural validator:
    ```bash
    python -c "from src.data.tax_rules.validator import validate_all; issues = validate_all(); print('OK' if not issues else chr(10).join(issues))"
    ```
    A healthy result is `OK`.

### How to update state brackets (about 10 minutes)

State brackets update by **dropping in a new CSV** — no code changes:

1. Download the new year's 50-state table from the Tax Foundation ("State Individual Income Tax Rates and Brackets", published each February) and save it in the same layout as the existing CSV.
2. Save it as `state_brackets_<YEAR>.csv` next to the old one. The loader discovers it automatically; earlier years keep their own files, and years beyond your newest CSV clamp to it (with a logged warning, so nothing fails silently).
3. Run `pytest` — the state data tests validate the parse.
4. **Verify your own state against its primary source** — for California, the FTB's published bracket tables (CA indexes its brackets annually, so it drifts every year). The Tax Foundation table gives 50-state breadth; primary-source verification gives depth where it matters to you.
5. Check `STATES_TAXING_SS` in `state.py` — states occasionally phase Social Security taxation in or out.

Until you add a year's CSV, projections use the latest one you have — a documented, conservative approximation (the same clamping federal applies beyond its newest enacted year).

For the full step-by-step checklist including IRMAA updates and state tax changes, see [`backend/src/data/tax_rules/ANNUAL_UPDATE_CHECKLIST.md`](../backend/src/data/tax_rules/ANNUAL_UPDATE_CHECKLIST.md).
