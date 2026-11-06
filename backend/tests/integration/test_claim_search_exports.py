"""The "Claim-age search" section in csv / xlsx / pdf for a joint run."""
from __future__ import annotations

import io
import json

import pytest
from src.optimization.joint import run_joint_optimization
from src.reports import claim_search
from src.reports.csv_export import yearly_plan_csv
from src.reports.pdf_export import build_pdf
from src.reports.xlsx_export import build_xlsx
from tests.integration.test_joint import ENGINES, SEARCH_BOTH, SMALL, _couple


@pytest.fixture(scope="module")
def joint_result() -> dict:
    state, settings, constraints = _couple()
    result = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH, SMALL)
    return json.loads(json.dumps(result, default=float))  # as stored


def test_tables_label_the_screening_stage_and_carry_every_pair(joint_result):
    titles = {t[0]: t for t in claim_search.tables(joint_result)}
    pairs = titles["Claim-age pairs — initial comparison, 2 market scenarios"]
    assert "Best strategy (first 2)" in pairs[1] and "Score (all 6)" in pairs[1]
    assert len(pairs[2]) == 4
    assert {"Strategies tested using all 6 market scenarios", claim_search.COMPARED_WITH_YOURS,
            "Search assumptions"} <= set(titles)
    finalists = titles["Strategies tested using all 6 market scenarios"][2]
    assert any(r[-1] == "Recommendation" for r in finalists)
    # The page's words: readable candidates, the shared verdict labels.
    assert not any("@" in str(r[0]) for r in finalists)
    assert {r[-1] for r in finalists} <= {
        "Recommendation", "Recommendation ahead", "Alternative ahead",
        "Too close to distinguish", "Practically equivalent", ""}
    summary = dict(claim_search.summary_rows(joint_result))
    w = joint_result["winning_policy"]
    ages = f"You {w['claim_age_self']} · Spouse {w['claim_age_spouse']}"
    assert summary["Recommended claim ages"] == ages


def test_an_older_run_never_compares_screening_with_a_full_sample_score(joint_result):
    old = json.loads(json.dumps(joint_result))
    del old["search"]["stages"]["winner_stage1_score"]
    pairs = {t[0]: t for t in claim_search.tables(old)}[
        "Claim-age pairs — initial comparison, 2 market scenarios"]
    col = pairs[1].index("vs recommendation (first 2)")
    assert all(r[col] == "" for r in pairs[2])
    assert "Screening comparison unavailable for this saved run" in pairs[3]


def test_longevity_checks_are_rows_per_strategy_and_columns_per_check(joint_result):
    titles = {t[0]: t for t in claim_search.tables(joint_result)}
    t = titles.get("What if you live longer or shorter? (not used to rank)")
    if t is None:
        pytest.skip("this small run has no longevity checks")
    _, header, rows, _ = t
    assert header[0] == "Strategy and claim ages"
    assert rows[0][0].startswith("Recommendation: ")
    assert rows[-1][0] == "Highest among the strategies checked?"
    assert not any("@" in str(r[0]) for r in rows)


def test_a_fixed_age_run_has_no_claim_search_section():
    assert claim_search.tables({"winning_policy": {}}) == []
    assert claim_search.summary_rows({"winning_policy": {}}) == []


def test_csv_has_the_section(joint_result):
    out = yearly_plan_csv(joint_result)
    assert "# Explore other Social Security claim ages" in out
    assert "Best strategy (first 2)" in out
    assert "# Recommended strategy compared with your original choices" in out


def test_xlsx_has_a_claim_age_search_sheet(joint_result):
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(build_xlsx(joint_result)))
    ws = wb["Claim-age search"]
    values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    assert "Explore other Social Security claim ages" in values
    assert "Claim-age pairs — initial comparison, 2 market scenarios" in values
    assert "Best strategy (first 2)" in values
    assert claim_search.COMPARED_WITH_YOURS in values
    res = [c.value for row in wb["Results"].iter_rows() for c in row]
    assert "Recommended claim ages" in res and "Conversions stop after" in res


def test_pdf_has_the_section(joint_result):
    from pypdf import PdfReader

    pdf = build_pdf(joint_result, {"filing_status": "joint", "state": "TX",
                                   "run_date": "2026-10-17"})
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Explore other Social Security claim ages" in text
    assert "Recommended claim ages" in text
    assert "compared with your original choices" in " ".join(text.split())
