# Annual Tax Data Update Checklist

This checklist is for anyone updating the tax data — no programming experience required for most steps. Follow them in order each year, typically in October–November. The goal is to keep the retirement projections accurate for the new tax year.

---

## Overview of files you will edit

| File | What it contains |
|------|-----------------|
| `backend/src/data/tax_rules/federal.py` | Federal income tax brackets, standard deductions, LTCG brackets |
| `backend/src/data/tax_rules/irmaa.py` | Medicare Part B and Part D premiums (IRMAA tiers) |
| `backend/src/data/tax_rules/state.py` | List of states that tax Social Security benefits |

---

## Step 1 — October: Download the IRS Revenue Procedure (Rev. Proc.)

Every October, the IRS publishes the inflation-adjusted tax numbers for the following year. This document is called the **Revenue Procedure** (abbreviated "Rev. Proc.").

**What to do:**
1. Go to [irs.gov](https://www.irs.gov) and search for "Revenue Procedure 20XX" (replace XX with the upcoming year, e.g. 2027 numbers come out in Rev. Proc. 2026-XX).
2. Download the PDF. It will be titled something like *Rev. Proc. 2026-45*.
3. Save it somewhere accessible (e.g. your Downloads folder). You will need it for Steps 2 and 3.

---

## Step 2 — Add a new `FederalTaxYear` entry in `federal.py`

Open `backend/src/data/tax_rules/federal.py` in a text editor. You will add a new block at the bottom of the `FEDERAL` dictionary by **copying the previous year's block and changing the numbers**.

**Example — copying the 2026 block to create 2027:**

Before (existing 2026 block ends like this):
```python
    2026: FederalTaxYear(
        year=2026,
        source="Rev. Proc. 2025-32 ...",
        brackets={
            "single": _b(("12400", "0.10"), ...),
            ...
        },
        ...
    ),
}
```

After (add the new 2027 block after the comma, before the closing `}`):
```python
    2026: FederalTaxYear(
        year=2026,
        source="Rev. Proc. 2025-32 ...",
        ...
    ),
    2027: FederalTaxYear(
        year=2027,
        source="Rev. Proc. 2026-XX (insert the actual Rev. Proc. number here)",
        brackets={
            "single": _b(("XXXX", "0.10"), ("XXXX", "0.12"), ...),
            ...
        },
        ...
    ),
}
```

Leave all dollar amounts as `"XXXX"` placeholders for now — you will fill them in during Step 3.

---

## Step 3 — Fill in brackets, LTCG thresholds, and standard deduction

Open the Rev. Proc. PDF you downloaded in Step 1. The key sections are:

- **§2.01** — Ordinary income tax brackets (the 10%, 12%, 22%, 24%, 32%, 35%, 37% rows)
- **§2.03** — Long-term capital gains (LTCG) thresholds (the 0%, 15%, 20% rows)
- **§2.09** (or nearby) — Standard deduction amounts

**What to enter:**

In the `"single"` bracket list, enter the **upper income bound** of each bracket (the last bracket uses `None`). Enter the tax rate as a decimal string (e.g. `"0.22"` for 22%).

Example for a fictional 2027 single filer (numbers made up):
```python
"single": _b(
    ("12700",  "0.10"),   # 10% on income up to $12,700
    ("51500",  "0.12"),   # 12% on income $12,701–$51,500
    ("109000", "0.22"),   # 22% on income $51,501–$109,000
    # ... continue for all 7 brackets ...
    (None,     "0.37"),   # 37% on all income above the last threshold
),
```

Do the same for `"joint"` (married filing jointly) brackets, LTCG brackets, and standard deductions.

---

## Step 4 — Check OBBBA special rules (SALT cap and senior bonus)

The One Big Beautiful Budget Act (OBBBA, P.L. 119-21) introduced two temporary provisions that need attention each year:

**SALT cap** (state and local tax deduction limit):
- The cap increases by approximately 1% per year through 2029: $40,000 (2025), $40,400 (2026), ~$40,808 (2027), etc.
- After 2029, the cap reverts to $10,000.
- Update the `SaltRule(cap={"single": D("XXXX"), "joint": D("XXXX")}, ...)` values in the new year's block.

**Senior bonus deduction** (`_SENIOR_BONUS`):
- This $6,000-per-person deduction applies **only for tax years 2025 through 2028**.
- In 2029 and beyond, remove `senior_bonus=_SENIOR_BONUS` or set `last_year=2028` (already coded; no action needed unless Congress extends it).

---

## Step 5 — November: Update IRMAA (Medicare Part B and Part D premiums)

Every November, the Centers for Medicare and Medicaid Services (CMS) publishes next year's Medicare premiums. Search for the **CMS press release** or the Federal Register notice (search "CMS Part B premium 20XX announcement").

Open `backend/src/data/tax_rules/irmaa.py` and add a new `IrmaaYear` block for the upcoming year, following the same copy-and-update pattern as Step 2.

Key values to enter:
- `part_b_standard` — the base monthly Part B premium (e.g. `"202.90"` for 2026)
- `tiers` — the MAGI thresholds and premium amounts for each IRMAA tier (single and joint)

The first tier's `part_b` amount must equal `part_b_standard`.

---

## Step 6 — Review states that tax Social Security benefits and update state tax brackets

### Part A: Social Security taxation rules

At the top of `backend/src/data/tax_rules/state.py`, find the `STATES_TAXING_SS` dictionary. Some states change their rules yearly.

Check a reliable summary (e.g. [AARP's state Social Security tax guide](https://www.aarp.org/retirement/social-security/questions-answers/which-states-tax-ss-benefits/)) for any states that newly exempted Social Security income or newly began taxing it.

Add or remove states from `STATES_TAXING_SS` as needed, and update the comment above it with the verification date and sources.

### Part B: State income tax brackets

State income tax brackets also change yearly. Open `backend/src/data/tax_rules/state_brackets_2025.csv` — this file contains the tax bracket thresholds for each state.

**To update for a new tax year, choose one of these:**

1. **Edit the CSV in place:** If only a few numbers changed, open `state_brackets_2025.csv` in a text editor or spreadsheet program and update the dollar amounts. Keep the same column layout (state, filing status, bracket threshold, tax rate, etc.).

2. **Replace with a new year's CSV:** If your tax authority provides a complete new CSV file for the next year, you can drop it in. Make sure it has the same columns as the old one. Then, in `state.py`, find the line that loads `state_brackets_2025.csv` and change the filename to match (e.g. `state_brackets_2026.csv`).

After making any bracket changes, re-run the tests in Step 7 to catch any formatting issues.

---

## Step 7 — Run the targeted tax data tests

Open a terminal, navigate to the project root (`~/projects/retirement-optimizer`), and run:

```bash
source .venv/bin/activate
pytest backend/tests/unit -k tax -v
```

You should see output ending in something like:

```
============================================================
38 passed in 0.14s
```

If any tests **FAIL**, the output will show which test failed and why. Fix the data entry error (usually a typo in a dollar amount or rate) and re-run until all tests pass.

---

## Step 8 — Run the validator

The validator catches structural problems that tests might not cover (such as brackets in the wrong order). Run it with:

```bash
source .venv/bin/activate
python -c "from src.data.tax_rules.validator import validate_all; issues = validate_all(); print('OK' if not issues else '\n'.join(issues))"
```

**Healthy output:** `OK`

**Problem output example:**
```
federal[2027]: brackets['single']: bracket uppers do not strictly ascend at index 2 (103350 >= 97000)
```

This means the single-filer bracket at index 2 has a smaller upper bound than the one before it — you transposed two numbers. Fix it in `federal.py` and re-run.

---

## Step 9 — Bump the version, commit, and tag

Once all tests pass and the validator is clean:

1. In `pyproject.toml`, increment the minor version number (e.g. `0.7.0` → `0.8.0`).

2. Commit everything:
   ```bash
   git add backend/src/data/tax_rules/federal.py \
           backend/src/data/tax_rules/irmaa.py \
           backend/src/data/tax_rules/state.py \
           pyproject.toml
   git commit -m "feat(tax-data): TY20XX federal brackets, IRMAA premiums, state SS updates"
   ```

3. Tag the release:
   ```bash
   git tag v0.8.0
   git push && git push --tags
   ```

4. Verify CI (automated checks) goes green on GitHub by running:
   ```bash
   gh run watch --exit-status
   ```

---

## Quick reference — what each variable name means

| Variable / field | Plain-English meaning |
|------------------|-----------------------|
| `brackets["single"]` | Tax rate tiers for a person filing alone |
| `brackets["joint"]` | Tax rate tiers for a married couple filing together |
| `ltcg_brackets` | Capital gains tax rate tiers (investments held > 1 year) |
| `standard_deduction` | The flat dollar amount the IRS lets you deduct without itemizing |
| `SaltRule.cap` | Maximum state and local tax you can deduct on federal return |
| `SeniorBonus.amount_per_person` | Extra deduction for each spouse aged 65+ (TY2025–2028 only) |
| `part_b_standard` | Base monthly Medicare Part B premium (what most people pay) |
| `IRMAA tiers` | Extra Medicare premiums charged to high-income retirees |
| `STATES_TAXING_SS` | States that include Social Security income in taxable income |

---

## State income tax (all 50 states + DC)

State brackets live in year-suffixed CSVs next to this file:
`state_brackets_2025.csv`, `state_brackets_2026.csv`, … The loader picks the
CSV matching the simulated year and clamps to the latest available year
(with a logged warning) when a year has no file — the same policy as federal.

**Annual update (about 10 minutes):**

1. Download the new year's 50-state individual income tax table from the
   Tax Foundation ("State Individual Income Tax Rates and Brackets",
   published each February) and export/save it in the same CSV layout as
   the existing file (two header rows, one row per bracket, state name on
   the first row of each block).
2. Save it as `state_brackets_<YEAR>.csv` in this folder. Nothing else
   changes — the loader discovers it automatically.
3. Run `pytest` — the state data tests validate the parse.
4. **Verify your own state against its primary source** (for California:
   the FTB's published bracket tables — CA indexes brackets annually).
   The Tax Foundation table gives 50-state breadth; primary-source
   verification gives depth where it matters to you.
5. Review `STATES_TAXING_SS` in `state.py` — states occasionally phase
   Social Security taxation in or out (WV completed its phase-out in 2026).
