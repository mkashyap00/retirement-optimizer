# Retirement Optimizer

A tax-optimized retirement planner: multi-year Roth conversion strategies, Social Security claim ages chosen together with them, withdrawal sequencing, and tax-lot sale planning — built on real federal and state tax engines, Monte Carlo simulation, and plain-English rationale narratives for every decision.

Every projection runs to the end of your horizon, including the years after the money would run out — because those are the years worth planning around, and a table that simply stops there tells you nothing about how short you fall.

Built for retirees and near-retirees who want to understand *why* a conversion strategy makes sense — not just a number to convert — with tax data they can read, verify, and update themselves each year.

This is an **annual-planning tool**: review the modeled recommendation — ideally with a CFP® professional or CPA — before acting on it, then re-run each year with your real balances and the latest tax data, so each year's decision is re-modeled with facts instead of projections.

---

## Features

- **Real tax engines, golden-tested** — federal income tax (brackets, LTCG stacking, NIIT, SALT), state income tax (all 50 states + DC), IRMAA (Medicare Part B/D surcharges), RMDs (SECURE 2.0 applicable age — 72, 73 or 75 by birth cohort — on the Uniform Lifetime Table, taken per IRA owner at that owner's age), and Social Security taxation including spousal and survivor benefits. Every engine is tested against hand-verified 1040 scenarios; all 48 Uniform Lifetime factors were checked against Pub. 590-B.
- **TY2025 and TY2026 data, verified vs primary sources** — Rev. Proc. 2024-40 (TY2025) and Rev. Proc. 2025-32 (TY2026), including the age-65 additional standard deduction, the OBBBA senior bonus deduction (phased out per person) and the SALT cap schedule.
- **BETR (Break-Even Tax Rate)** — tells you the future marginal rate that would make each conversion break even, following the Vanguard methodology (Vanguard, "A BETR approach to Roth conversions," July 2025).
- **Social Security claim ages, searched with the conversions** — for each person not already receiving benefits, the wizard can either hold your chosen claim age or let the optimizer try every eligible age from 62 to 70. Every claim-age pair gets its own conversion strategy, so the two decisions are made together rather than one after the other. A search runs in the background with a progress page; the results show how much the chosen ages and the conversions each add, and how the answer holds up if the plan ends five years earlier or later, or one of you dies at 78.
- **Per-year rationale narratives** — each projection year explains in plain English what bracket headroom was used, what thresholds were approached, and, in a year with no conversion, the reason the strategy gives for it.
- **IRMAA and NIIT awareness** — Medicare income surcharges are charged for each person on Medicare, and a setting decides whether conversions may cross a tier (*Allow* lets the cost decide; *Restrict* keeps a conversion below the next tier). NIIT on investment income is included.
- **What-if comparison** — compare your plan (**Baseline**) with a changed copy (**Your changes**): spending, Social Security claim ages, spending rule, first-death age and, under Advanced options, a forced conversion strategy, IRMAA policy, conversion window and caps. Both sides prefill from the plan's saved values, and every field you change is highlighted and listed above the Compare button. You get difference cards, an overlaid balance chart, and a **year-by-year table** — because two strategies can reach nearly the same lifetime conversion on opposite schedules, and only the rows show that.
- **Deterministic mode** — tick *Skip market simulation* to drop the randomness entirely and compare strategies on the steady-return projection alone. This is the interpretable baseline for reconciling against your own spreadsheet.
- **Spending guardrails (optional)** — model what happens if you'd cut back in bad markets (Guyton-Klinger: cut ~10% when the withdrawal rate drifts 20% above where it started, restore when it drifts below, never below your essential floor). Cuts are **charged**, not treated as free safety — otherwise "spend less" would look like costless resilience. With an essential floor entered, spending given up above it costs half as much as spending lost below it; without one, every reduction costs the full amount.
- **The widow's penalty** — model the first death as a what-if: the survivor files *single* (half the bracket widths, half the standard deduction), keeps the larger Social Security benefit and loses the smaller, while the RMDs continue. Usually the highest-tax stretch of a couple's retirement, and exactly what conversions hedge against.
- **Portfolio sale planner** — upload your positions once (total cost basis; no lot dates needed) from the top-nav **Portfolio** tab, and every plan reuses them. Produces a suggested sell list for the first projected taxable withdrawal, in tax-priority order (losses first, then the smallest gain per dollar raised), splitting in a conversion year how much funds spending and how much the conversion's taxes — downloadable as a dated CSV or PDF sale plan. Refresh your holdings and rerun the plan each year.
- **CSV, Excel, and PDF export** — download the full year-by-year projection as a spreadsheet, multi-sheet workbook (inputs, plan, alternatives, tax-audit worksheet, native charts), or formatted report; all three are auto-saved for every run and stamped with the run and plan IDs.
- **Runs on your machine** — saved plans and results are stored in a local DuckDB database. Reports are saved separately (in `reports/`), and unfinished wizard drafts are stored in your browser. Optional cloud AI summaries send selected financial information to the configured provider (never names, birth dates, state or portfolio positions); nothing else leaves your computer.
- **Optional AI summary** — configure the Anthropic API *or* a local OpenAI-compatible LLM (llama.cpp, LM Studio, Ollama, vLLM) for a one-button, privacy-scoped narrative that explains the strategy in plain English. With a local model, nothing leaves your machine.

---

## How the optimizer works

**From inputs to a recommendation.** The wizard collects your household in six steps — household (including the age to plan through, 95 by default), assumptions, accounts, income and Social Security, spending and goals — then its Review and run step asks nothing new: one summary with an Edit link per step, the strategies that will be compared, and a single action: **Optimize conversions** when every claim age is fixed, or **Optimize conversions and claim ages** when at least one is searched. A fixed-age run finishes in under a minute and opens its results. A claim-age search takes a few minutes, so it runs in the background: a progress page shows each stage (compare strategies, test market outcomes, check longevity, prepare results), the header shows *Search running · View progress* on every page, and the progress page opens the results when it is done. For Social Security, each person says whether benefits have started; if not, whether the optimizer finds the best eligible age (with an optional age of your own to compare against) or uses an age you choose. Each dashboard card has one action — **View results**, **View progress**, or **Finish setup and run** for a plan saved but never run — and a delete icon; changes to a saved plan go through a copied **New Plan** or the **What-if** page.

Every candidate conversion strategy is simulated over your **entire planning horizon** with the real tax engines. The candidates are no conversions; filling the 10, 12, 22, 24 or 32% bracket every year; converting a fixed amount each year — 5, 10 or 20% of the starting traditional balance, named in dollars (*Convert up to $50,000 annually*); and each of those rules stopped after a given year — typically 40 to 110 strategies, built once each on a steady-return projection. How they are then narrowed depends on the run:

- **Claim ages fixed:** every strategy is simulated on the first 100 of 300 shared market scenarios; the three leaders and *no conversions* are carried to all 300.
- **Claim ages searched:** for each eligible claim-age pair, the three best strategies on the steady-return projection plus *no conversions* (and every strategy at the comparison ages you entered) are screened on 50 scenarios; the five best are carried to all 300, along with every strategy at your comparison ages and *no conversions* at the winning ages.

Either way only fully scored strategies are ranked (the exports show how many scenarios each received). [How a recommendation is chosen](docs/HOW_A_RECOMMENDATION_IS_CHOSEN.md) walks four households through this. Each strategy is scored:

> **modeled score = average over market scenarios of ( PV(terminal estate, heir-adjusted) − λ · unfunded spending )**

Taxes count through the estate: every tax dollar paid is a dollar the estate no longer holds, so lifetime taxes are reported beside the score rather than subtracted a second time. Heir-adjusted means traditional-IRA dollars count at (1 − heir tax rate). **λ = 1**: one present-value dollar of essential spending the plan fails to fund costs one dollar of estate (spending cut above your essential floor costs 50¢). The same formula ranks strategies in the single-path search and in Monte Carlo. Social Security grows by a COLA (your inflation rate by default), and after the latest published year, selected federal and Medicare thresholds and California's brackets and deductions increase with your inflation assumption; other state tables stay as last published (see the guide for exceptions and limitations). (Until October 2026 an *Optimization Priority* setting traded lifetime taxes against the estate; runs saved before then keep that label.)

**Reading the results.** The page leads with the **Recommended strategy** — the claim ages, the conversions and the first year's amount — and a sentence on how clearly it beats its closest alternatives. A short box, **How we simulate market outcomes**, then explains the two kinds of number with the run's recorded assumptions: the **modeled score** and the share of **scenarios with spending funded** come from 300 market scenarios (returns varying year to year around your assumed average); the estate, taxes, charts and year-by-year table come from a **steady-return projection** at that average. **Recommended strategy compared with your original choices** compares the recommendation with your plan as *from → to* (for example *Your ages 65 / 63 → Recommended ages 69 / 68*; hidden, with a one-line note, when there is nothing to compare), showing both outcomes — average score, after-tax estate, unfunded spending, scenarios funded — and the difference. **Close alternatives** ranks the nearest strategies the way the optimizer did, by average modeled score across the market scenarios, and names any it cannot clearly separate from the recommendation; their steady-return tax and estate differences sit under *Compare taxes and estate assuming a steady return* (at your assumed rate). Each comparison result is *Recommendation ahead*, *Alternative ahead*, *Practically equivalent* (similar enough to treat alike under the model's comparison threshold) or *Too close to distinguish* (not enough evidence to say which is better), explained beside Close alternatives; a ranking is never claimed where the simulation cannot support one. A claim-age search adds **Explore other Social Security claim ages**, a grid you can inspect without running anything, and **What if you live longer or shorter?**.

**Want the interpretable version instead?** Tick **Skip market simulation** on the What-if page and every year grows at exactly your Expected Return — no randomness, no averaging. Pair it with the Strategy option to line the bracket-fill rules up against each other. The headline estate and tax projections use a steady annual return. The modeled score and spending-success figures use the market simulations, which recalculate the plan under different yearly returns.

The User Guide has screenshots of every wizard step and results section, and is also available as a web page, [`docs/USER_GUIDE.html`](docs/USER_GUIDE.html), to open in a browser from your copy of the project. How to read every part of the results — the modeled score, the comparisons, the claim-age grid and the lifespan checks — is in the **[User Guide → Understand your results](docs/USER_GUIDE.md#4-understand-your-results)**, and the model's boundaries in [Assumptions and limits](docs/USER_GUIDE.md#9-assumptions-and-limits).
For a step-by-step walkthrough of the search with four example households and reproducible
numbers, see **[How a recommendation is chosen](docs/HOW_A_RECOMMENDATION_IS_CHOSEN.md)**. For the
code-level account — the full candidate list, the joint claim-age search, the staged Monte Carlo
budget and the per-year funding solver — see **[Optimizer internals](docs/OPTIMIZER_INTERNALS.md)**.

---

## 🔄 Updating tax law data (no programming required)

Tax brackets, deductions, and Medicare premiums change every year. This project stores all tax rules as **plain, commented data files** — one block per tax year, each citing its IRS or CMS source. Updating for a new year takes about 15 minutes:

1. Copy the latest year's block in `backend/src/data/tax_rules/federal.py`.
2. Change the year number and update the dollar amounts from the IRS Revenue Procedure (published each October).
3. Run `pytest` — the built-in validator catches structural mistakes like transposed numbers or missing brackets. Passing tests do not prove the new amounts are right; check each against the IRS publication.

No Python knowledge is required to read or edit these files. The numbers are formatted as plain decimal strings with inline comments explaining each field.

Full step-by-step instructions: [`backend/src/data/tax_rules/ANNUAL_UPDATE_CHECKLIST.md`](backend/src/data/tax_rules/ANNUAL_UPDATE_CHECKLIST.md)

Checking the numbers against IRS worksheets or your own spreadsheet: [`docs/VERIFYING_RESULTS.md`](docs/VERIFYING_RESULTS.md)

---

## Quickstart

### With the start script (recommended)

Install [Git](https://git-scm.com/), [Python 3.12](https://www.python.org/downloads/) and [Node.js 20.9+](https://nodejs.org/) first ([`docs/INSTALL.md`](docs/INSTALL.md) walks through it); the scripts install the project's own dependencies, not these.

**macOS / Linux:**
```bash
git clone https://github.com/mkashyap00/retirement-optimizer.git
cd retirement-optimizer
bash scripts/start.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/mkashyap00/retirement-optimizer.git
cd retirement-optimizer
.\scripts\start.ps1
```

Then open **http://localhost:3000** in your browser.

> The first run installs the Python and Node dependencies, which takes a few minutes. Every launch rebuilds the frontend, so later starts still take a minute or so.

> The API has no login, so both servers listen on this computer only (`127.0.0.1`). Setting `BIND_HOST=0.0.0.0` makes every saved household readable and deletable by anyone who can reach the port; do that only on a network you trust completely.

### Manual commands

```bash
# Backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e .
uvicorn src.api.app:create_app --factory --port 8000

# Frontend (separate terminal)
npm install --prefix frontend
npm run dev --prefix frontend -- -H 127.0.0.1
```

### Updating an existing install

```bash
git pull
pip install -e .                      # picks up new Python dependencies (e.g. httpx)
npm ci --prefix frontend              # the start scripts do this automatically when the lockfile changes
npm run build --prefix frontend       # only if you run the production frontend by hand
```

Then re-run your plans: saved runs keep the numbers they were made with.

### Optional: AI summary

```bash
cp .env.example .env
# Option A — Anthropic API:
pip install -e ".[llm]"          # then set ANTHROPIC_API_KEY=your_key in .env
# Option B — a local LLM (fully private, no extra install):
#   set LLM_BASE_URL=http://localhost:8080/v1 and LLM_MODEL=your-model in .env
```

With a local OpenAI-compatible server (llama.cpp, LM Studio, Ollama, vLLM) nothing leaves your machine. Details, including exactly what is sent: [`docs/USER_GUIDE.md` — Data, privacy and optional AI summaries](docs/USER_GUIDE.md#8-data-privacy-and-optional-ai-summaries).

Full installation walkthrough: [`docs/INSTALL.md`](docs/INSTALL.md)

Day-to-day commands — resetting the database, restarting the servers, running on a different port: [`docs/CLI_CHEATSHEET.md`](docs/CLI_CHEATSHEET.md)

---

## Architecture

FastAPI backend (Python 3.12) + Next.js 16 frontend (React 18; Node 20.9+). Tax engines are pure functions with no database dependency; DuckDB persists households, run results, and the app-level portfolio (keyed to a default profile).

```
retirement-optimizer/
├── backend/
│   └── src/
│       ├── api/              # FastAPI app, endpoints, Pydantic models
│       ├── data/tax_rules/   # Tax data files (federal, IRMAA, state, RMD)
│       ├── engines/          # Tax calculation engines (pure functions)
│       ├── optimization/     # Optimizer, claim-age search, Monte Carlo, BETR, spending rules
│       ├── rationale/        # Per-year narrative generator
│       ├── portfolio/        # Tax-lot sale planner
│       └── reports/          # CSV, Excel, PDF, and dated sale-plan export
├── frontend/
│   └── src/
│       ├── app/              # Next.js pages (wizard, search progress, results, compare, portfolio)
│       ├── components/       # React components
│       ├── lib/              # API client, types, utilities
│       └── stores/           # Zustand state stores
├── scripts/
│   ├── start.sh              # macOS/Linux launcher (PORT=3005 to override the frontend port)
│   ├── dev.sh                # hot-reload launcher for development
│   ├── start.ps1             # Windows launcher
│   ├── db_reset.py           # drop + recreate the database (fresh start)
│   ├── db_purge.py           # delete all rows, keep the schema
│   └── db_clear_portfolio.py # delete only the uploaded portfolio
├── docs/
│   ├── INSTALL.md            # Non-technical installation guide
│   ├── USER_GUIDE.md         # User guide: wizard, results, What-if, portfolio, exports, privacy
│   ├── USER_GUIDE.html       # The same guide as a web page (generated: scripts/build_user_guide_html.py)
│   ├── images/user-guide/    # Screenshots used by the User Guide
│   ├── USER_GUIDE_DEPRECATED.md  # Previous user guide, kept for its history
│   ├── VERIFYING_RESULTS.md  # Tax Audit sheet, cross-checks, spreadsheet reconciliation
│   ├── HOW_A_RECOMMENDATION_IS_CHOSEN.md  # The search walked through four example households
│   ├── Retirement-Optimizer-plain-English.pdf  # Slide deck: what the app decides and how, for any reader
│   ├── Retirement-Optimizer-technical.pdf      # Slide deck: objective, pipeline, the four examples
│   ├── OPTIMIZER_INTERNALS.md    # How candidates are built, scored and compared
│   ├── OPTIMIZER_HISTORY.md      # Dated archive: retired greedy search, past measurements
│   └── CLI_CHEATSHEET.md     # Reset the DB, restart servers, common commands
├── pyproject.toml
└── .env.example
```

### Code that looks unused but is not

Three kinds of code live side by side. Before deleting something no production
path calls, check which kind it is.

- **Production code** — what the app runs: `backend/src/` and `frontend/src/`.
- **Compatibility code for saved runs and plans.** Runs and plans saved by
  earlier versions must still load and read correctly, so some code serves only
  them: the greedy policy names in `backend/src/reports/policy_labels.py` and
  `frontend/src/lib/policyLabels.ts` (`LEGACY_POLICY_LABELS`), the deprecated
  `estate_weight` input and its stored label, the "legacy reading" of Social
  Security status, and the older portfolio CSV layouts. These are marked
  *legacy* or *deprecated* in comments.
- **Benchmark and reference code** — `backend/benchmarks/`. It reproduces
  documented measurements and is run by hand. `greedy_reference.py` is the
  retired greedy search kept as the benchmark's reference, and it is why
  `generate_conversions` still sizes `fill_irmaa_tier`, `level_25/50/100` and
  `max_pre_rmd`, which the production search never requests.

CI runs `ruff check backend/`, the backend tests, a TypeScript check with
unused locals and parameters as errors (`npm run typecheck`), the frontend build
and the frontend tests.

---

## Testing

```bash
# Backend (the test tools are an optional extra)
source .venv/bin/activate
pip install -e ".[dev]"
pytest

# Frontend
npm test --prefix frontend -- --watchAll=false

# Frontend type check (unused locals and parameters are errors) and build
npm run typecheck --prefix frontend
npm run build --prefix frontend

# Ruff lint
ruff check backend
```

**1,295 tests** at the time of writing — 907 backend, 388 frontend. The backend
suite includes a golden fixture (`backend/tests/integration/golden_standard_household.json`)
that pins the winning policy and its headline numbers for a standard household.
If a change moves it, **inspect the diff and confirm the new numbers are right
before regenerating** with `pytest --regen-golden` — a moving golden is the
signal the change worked, and also exactly how a real bug slips in.

---

## Disclaimer

This is an educational tool for exploring retirement planning strategies. It is **not tax advice**. Tax laws are complex and individual circumstances vary. Verify any strategy with a qualified CPA or financial advisor before acting on it.

---

## License

MIT — see [LICENSE](LICENSE).
