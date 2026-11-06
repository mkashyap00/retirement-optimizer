"""Export labels for run assumptions (shared by PDF and Excel)."""
from src.reports.assumption_labels import ss_cola_label


def test_snapshot_without_the_key_is_a_flat_benefit_run():
    assert ss_cola_label({"inflation": 0.03}) == "None (benefits held flat)"


def test_null_follows_inflation_floored_at_zero():
    assert ss_cola_label({"inflation": 0.03, "ss_cola": None}) == "Follows inflation (3.0%)"
    assert ss_cola_label({"inflation": -0.01, "ss_cola": None}) == "Follows inflation (0.0%)"


def test_explicit_rates():
    assert ss_cola_label({"inflation": 0.03, "ss_cola": 0}) == "None (benefits held flat)"
    assert ss_cola_label({"inflation": 0.03, "ss_cola": 0.025}) == "2.5%"


def test_objective_row_for_new_and_old_runs():
    from src.reports.assumption_labels import NEW_OBJECTIVE_LABEL, objective_row
    new = {"objective": "pv_estate_minus_weighted_shortfall"}
    assert objective_row(new, {"estate_weight": 0}) == ("Objective", NEW_OBJECTIVE_LABEL)
    assert objective_row({}, {"estate_weight": 0}) == ("Optimization priority", "Lifetime taxes")
    assert objective_row({}, {"estate_weight": 0.5}) == ("Optimization priority", "Balanced")
    assert objective_row({}, {}) == ("Optimization priority", "Estate")


def test_tax_tables_label():
    from src.reports.assumption_labels import tax_tables_label
    assert tax_tables_label({}) == "Frozen at the last published year"
    label = tax_tables_label({"tax_tables": {
        "federal_published_through": 2026, "irmaa_published_through": 2026,
        "state_published_through": 2025, "state_indexed": ["CA"],
        "indexation_rate": 0.03, "irmaa_premiums_projected": False}})
    assert "through 2026" in label and "3.0%" in label and "CA only" in label
