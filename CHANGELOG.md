# Changelog

All notable changes to this project are documented here.

## [Unreleased] — October 2026

### Capital gains already realized this year
- **New inputs on Income & Social Security: "Investment gains already realized in <year>".** Net short-term and long-term gain or loss from sales already made this year, and the short- and long-term capital loss carried over from last year. They were missing entirely: the projection taxed only the gains of its own planned sales, so a household that had already realized gains got a first-year conversion that was too large and a tax estimate that was too low.
- They change the tax only, never the cash (the sale proceeds are already in the balances). Each year nets them with the gains of the plan's own sales as Schedule D does: a net short-term gain is ordinary income and uses up bracket room, a net long-term gain is taxed at capital-gains rates (and counts toward the net investment income tax and Social Security taxation), a net loss is deducted up to $3,000 and the rest carries forward with its character. Conversion sizing sees them too.
- Most states use the federal result as it is (New York, for example, takes these amounts from the federal return). California and Wisconsin allow $3,000 a year with their own carryover figured on state income (Wisconsin's limit rose from $500 in 2023). Pennsylvania and New Jersey allow no loss against other income and no carryover.
- They apply to the year entered only; the section shows that year, a plan or draft from an earlier year offers **Start <this year> entries** rather than relabelling them, and a plan run in a later year ignores them and says so in its advisories. Money fields now read a typed or pasted amount the same way while typing and after leaving the field (a pasted "$10,000" was cleared on leaving it). The Tax Audit sheet adds the net short-term gain, the capital loss deduction and a Schedule D block (already realized, from the plan's sales, carried in, carried forward); Review, the run's inputs and the AI summary list them.

### Social Security claim ages, chosen with the conversions
- The wizard asks whether each person already receives benefits and, for each person who does not, whether to hold the chosen claim age or **find the best eligible age** (62–70, less the ages a salary makes ineligible, each listed with its reason).
- A claim-age search runs in the background: a progress page with its stages, a header indicator on every page, and **View results** when done.
- Each person is asked in order: already receiving? (Yes: the age benefits started, fixed); if not, **Find the best eligible age** or **Use an age I choose** — the age selector appears only for the second. A searched age takes an optional comparison age; left blank, the results compare conversions at the recommended ages and show no "your ages" comparison (none is invented). Runs that would hold a blank age fixed are refused.
- Each claim-age pair gets its own conversion strategy; an initial comparison on 50 market scenarios, finalists on all 300 (the first 50 among them), lifespan checks (plan ends 5 years earlier or later; either spouse dies at 78) reported but not used to rank.

### Optimizer
- Greedy rollout strategies removed; level-dollar rules (5/10/20% of the starting IRA a year) and `…_thru_YYYY` stop-year variants added; Monte Carlo scores every strategy.
- *No conversions* is always fully sampled and ranked with the finalists, so it can win after full evaluation.
- A year without a conversion states the reason the strategy gives; an RMD is named as the cause only when it leaves no bracket room.

### Wizard and dashboard
- Six steps: spending moved to its own **Spending and goals** step; **Review and run** only summarizes, with Edit links, the projection's end year and the strategies to be compared, and starts the run.
- **Plan through age** is required for each person and starts at 95, a stated modeling default. Plans saved with it blank keep their 30-year projection when copied.
- Spending wording: *How much would you like to spend each year?* — household spending in today's dollars, excluding income taxes, before subtracting Social Security or other income; *Minimum annual spending* for planned cuts, with a blank explained.
- The Medicare surcharge setting offers two choices (allow crossing, surcharge counted; or restrict at thresholds); older *Ignore/Soft/Strict/Avoid* values keep their behaviour.
- Dashboard cards: one action for the plan's state — **View results**, **View progress** while a search runs, or **Finish setup and run** for a plan saved but never run (Review for that same plan, no copy; its claim-age choices are kept, or confirmed when this browser has no record of them) — and a **Delete plan** icon. *Run a new optimization* and the per-plan Portfolio link were removed; Portfolio stays in the top bar.
- A single filer's plan is saved without leftover spouse fields.
- **Advanced settings** (Assumptions) and **Optional goals and limits** (Spending) are always shown instead of collapsed, so their inputs are not missed; the Medicare surcharge setting has a tooltip explaining IRMAA and its cliff.
- **Year Roth opened** is required for a Roth with a balance (the 5-year-rule warning depends on it) and shows on the account's collapsed line; the step's error summary names the account (*Account 3 · year Roth opened*) instead of an internal field key.

### Reliability and maintenance
- **Shutdown waits for the search.** Stopping the server closes the database only once a running search has stopped; a search busy between progress reports, or saving its results, keeps the database open rather than writing to a closed one.
- **AI summary reflects the recommendation.** The prompt now names the strategy, the claim ages you entered and the claim ages recommended (separately), the modeled score and scenarios funded from the market scenarios, the steady-return figures labelled as such, the comparison with your entered ages, and each alternative with its own claim ages and comparison label.
- **A plan whose runs cannot be loaded says so** on the dashboard, with **Try again**, instead of an endless "…".
- Failed household saves and deletes are logged with the operation and traceback, never the plan's figures; failed background searches log their phase and elapsed time.
- Internal: API errors carry their status and the server's detail (no more parsing error text); policy names moved to `lib/policyLabels.ts`; the wizard's steps are one file each; unused components and five Radix packages removed; household snapshots and sale plans are ordinary modules rather than imports between endpoints; the four identical user-plan benchmark fixtures merged into one (results unchanged).
- CI type-checks the frontend with unused locals and parameters as errors.

### Documentation
- **New User Guide** (`docs/USER_GUIDE.md`), written from scratch for everyday use: key features, what to collect, the six wizard steps, running and recovering plans, reading the results, What-if, the portfolio, exports and what to take to a professional, data and AI privacy (including exactly what an AI provider receives), assumptions and limits, and common questions. The previous guide is kept as `docs/USER_GUIDE_DEPRECATED.md`.
- **`docs/VERIFYING_RESULTS.md`** — the built-in identities, the Tax Audit sheet, external cross-checks and reconciling against your own spreadsheet, moved out of the user guide.
- **`docs/HOW_A_RECOMMENDATION_IS_CHOSEN.md`** — the strategy menu, stop-year variants, what makes a strategy shrink or disappear, the staged screening and ranking, and the claim-age search, followed through four example households. Every table is produced by `backend/benchmarks/walkthrough.py`, so the figures can be regenerated.
- **Optimizer internals §1 corrected** — `fill_irmaa_tier`, `level_25/50/100` and `max_pre_rmd` are sized by `generate_conversions` but never requested by the search, so they are not strategies; the table now lists the five bracket fills and the three level amounts that are.
- **User Guide screenshots and web page** — 20 screenshots of a fictional example couple (every wizard step, the progress page, each results section, What-if and Portfolio) in `docs/images/user-guide/`, placed beside the text they illustrate. `docs/USER_GUIDE.html` is generated from the Markdown by `scripts/build_user_guide_html.py`, with a contents sidebar and working section links.
- **Slide decks replaced** — `docs/Retirement-Optimizer-plain-English.pdf` (16 slides) and `docs/Retirement-Optimizer-technical.pdf` (18 slides) follow the new walkthrough: the strategy menu, stop-year variants, the staged screening, the example couple's numbers and, in the technical deck, all four households and the claim-age search. The two `TLDR` decks they replace described the retired greedy search. A review pass corrected both decks and the walkthrough: first-shortfall years now come from the evaluated path (the script derived them from schedule length, one year late), the tight household's conclusion distinguishes small conversions from large ones (a pinned contrast strategy makes the eliminated strategy's score reproducible), the privacy line names the optional cloud AI summary, and the plain deck explains the modeled score against the steady-return value before the search machinery.
- **`docs/OPTIMIZER_HISTORY.md`** — a dated archive of the greedy-era policy table, the gate that retired greedy rollouts, the removed Monte Carlo cut and the funding-solver measurements, moved out of `OPTIMIZER_INTERNALS.md`, which now describes only the current pipeline and lists the benchmark commands.
- **Documentation corrections** — staged screening (not every strategy gets 300 scenarios), the discount rate can affect comparisons, *Plan through* ages set only the projection's end, salary-related claim-age exclusions are a modeling restriction, What-if starts from saved claim ages, drafts expire after 24 hours, the cash-flow identity includes surplus and shortfall, and shortfalls are penalties rather than a funded-first rule.

### Results wording
- The **Modeled score** card says what it measures (*Average after-tax estate minus spending-shortfall penalties · Today's dollars · 300 market scenarios*); the estate card is **Projected estate at a steady 6% annual return** (the run's own rate), *At the end of your plan*, *Equivalent to $… today*.
- *How much it helps* is now **Recommended strategy compared with your original choices**, titled with the ages (*Your ages 65 / 63 → Recommended ages 69 / 68*). With no comparison ages and no conversions it is replaced by one line: *No comparison claim ages were provided.*
- **What the comparison labels mean** moved beside Close alternatives, in plain words; the interval, median and dollar threshold sit under **Technical details**.

### Results, What-if and exports
- Fixed-amount strategies are named in dollars (*Convert up to $50,000 annually through 2029*: 5, 10 or 20% of the starting traditional balance, recorded with each new run); the recommendation states the years it actually converts in.
- Results lead with the **Recommended strategy**, then **How much it helps**, **Close alternatives**, and (for a search) **Explore other Social Security claim ages** and **What if you live longer or shorter?**. Every figure names its basis: the modeled score over market scenarios, or the steady-return projection; a short box states the run's recorded market assumptions (average return, volatility).
- **How much it helps** states each comparison as *from → to* (e.g. *Your entered ages → Recommended ages*) with both outcomes side by side: average modeled score, after-tax estate, unfunded spending and scenarios funded. **Close alternatives** now ranks strategies on the average modeled score across the market scenarios (the measurement that chose the recommendation); the steady-return tax and estate differences moved under *Compare taxes and estate assuming a steady 6% return*. The banner names the alternatives the simulation cannot clearly separate from the recommendation. Exports follow the same layout. Fixed-age runs now store each alternative's own score and the no-conversion baseline's estate and unfunded-spending breakdown.
- Comparisons use four labels: *Recommendation ahead*, *Alternative ahead*, *Practically equivalent*, *Too close to distinguish*.
- The results page no longer starts calculations: *Run this policy* is removed (older forced runs still open), and claim-age cells are inspect-only.
- Charts mark salary end, Social Security claims and the first RMD; each year row has an expand button.
- What-if compares **Baseline** with **Your changes**, highlights changed fields and lists them before Compare.
- An essential spending floor applies only with *Cut back, then recover*. A floor typed there and left behind by switching back to *Keep spending the same* was still listed as a change on What-if and applied to the comparison, charging spending missed above it at half weight; a plan saved after the same switch would have stored it too.
- CSV, Excel and PDF use the page's labels and add the claim-age search tables.

## [1.0.0] — 2026-07-05

### Summary

Complete rebuild of the retirement optimizer from scratch. The 2025 prototype (`retirement-optimizer-v2`) was retired after review found it used placeholder tax math that did not reflect actual IRS rules. This release enforces a single source of tax truth, golden-tests every engine against hand-verified 1040 scenarios, and delivers a full-stack web application.

### What's new

#### Tax data as code (Plans 01–02)
- All federal tax parameters (brackets, standard deductions, LTCG thresholds, SALT cap, senior bonus deduction) live in `backend/src/data/tax_rules/federal.py` as version-controlled, commented data — one block per tax year, each citing its IRS source.
- TY2025 data verified against Rev. Proc. 2024-40. TY2026 data verified against Rev. Proc. 2025-32, including OBBBA provisions (SALT cap $40,400, senior bonus $6,000/person TY2025–2028).
- IRMAA tiers for TY2025 and TY2026 verified against CMS press releases.
- RMD Uniform Lifetime Table from IRS Reg. §1.401(a)(9)-9.
- State income tax brackets for all 50 states + DC.
- Structural validator catches out-of-order brackets, missing years, and other data errors.
- `ANNUAL_UPDATE_CHECKLIST.md` guides a non-programmer through the yearly update in under 30 minutes.

#### Tax engines (Plan 03)
- Federal engine: ordinary income tax with bracket stacking, standard deduction, LTCG/QD preferential rates stacked above ordinary income, NIIT (3.8% on net investment income above thresholds), SALT deduction with OBBBA phase-down.
- State engine: loads per-state brackets from CSV; applies Social Security exemption rules for states that do not tax SS.
- IRMAA engine: two-year lookback; models all Part B and Part D tiers for single and joint filers.
- RMD engine: Uniform Lifetime Table; handles first-year deferral election.
- Social Security engine: provisional income calculation; 0%/50%/85% inclusion tiers per filing status.
- All engines golden-tested against hand-verified 1040 scenarios (Plan 03 benchmark suite).

#### Optimizer (Plan 04)
- Greedy rollout search across seven conversion policies (no conversion, fill to each of the seven federal brackets, fill to IRMAA cliff).
- Monte Carlo scoring: 1,000 simulations with stochastic return sampling; reports success probability.
- BETR (Break-Even Tax Rate): per-conversion metric following Vanguard's July 2025 methodology.
- Constraint support: IRMAA policy (ignore / soft / strict / avoid), conversion window, marginal rate limit, max conversion per year, target estate, preserve taxable flag.

#### API and persistence (Plan 05)
- FastAPI application with DuckDB persistence.
- Endpoints: `POST /households`, `GET /households`, `GET /households/{id}`, `POST /optimize`, `GET /runs/{id}`, `GET /households/{id}/runs`, `GET /health`.
- Pydantic v2 models throughout; all request/response shapes validated.

#### Rationale narratives (Plan 06)
- Per-year rationale generator produces structured `YearRationale` objects for every projection year.
- Narrative templates cover: bracket headroom used, IRMAA threshold proximity, BETR verdict, RMD interaction, no-conversion rationale.
- BETR verdict (favorable / marginal / unfavorable) and threshold warnings (amber / red) included in rationale output.

#### Frontend (Plan 07)
- Five-step planning wizard (Profile → Assumptions → Accounts → Income & SS → Spending & Review).
- Results page: four KPI cards, balances chart, tax breakdown chart, Roth conversion chart, year-by-year table with expandable rationale panel.
- Dashboard: household list with quick navigation to results.
- 106 frontend tests (Vitest/Testing Library).

#### Exports, comparison, portfolio, AI (Plan 08)
- CSV export: all per-year projection data as a spreadsheet-compatible file.
- PDF export: formatted report with charts and year table (ReportLab).
- Scenario comparison: run two strategies with different constraints side by side; delta table and overlay chart.
- Portfolio tax-lot sale planner: accepts brokerage CSV, returns tax-optimized sell order.
- Optional LLM narrative: `POST /runs/{id}/narrative` generates a plain-English strategy summary via the Anthropic API (requires `ANTHROPIC_API_KEY`; install `pip install -e ".[llm]"`).

#### Packaging and docs (this release)
- `scripts/start.sh` and `scripts/start.ps1` — one-command launchers for macOS/Linux and Windows.
- `docs/INSTALL.md` — non-technical installation guide.
- `docs/USER_GUIDE.md` — field explanations, results guide, tax data update walkthrough.
- `README.md` — full rewrite with features, quickstart, architecture, and prominent tax-update section.
- `pyproject.toml` version bumped to `1.0.0`.
- `.env.example` updated to document `NEXT_PUBLIC_API_URL`.
