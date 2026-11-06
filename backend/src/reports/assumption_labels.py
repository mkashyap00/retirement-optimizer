"""Plain-English labels for run assumptions, shared by the PDF and Excel exports.

The frontend's InputsPanel uses the same wording, so every surface describes a
run the same way.
"""
from __future__ import annotations


def ss_cola_label(settings: dict) -> str:
    """The Social Security COLA a run used, from its stored input snapshot.

    Snapshots saved before the setting existed carry no ``ss_cola`` key at all;
    those runs held benefits flat in nominal dollars.
    """
    if "ss_cola" not in settings:
        return "None (benefits held flat)"
    cola = settings["ss_cola"]
    if cola is None:
        inflation = max(0.0, float(settings.get("inflation") or 0))
        return f"Follows inflation ({inflation * 100:.1f}%)"
    if float(cola) == 0:
        return "None (benefits held flat)"
    return f"{float(cola) * 100:.1f}%"


_PRIORITY = {1.0: "Estate", 0.5: "Balanced", 0.0: "Lifetime taxes"}
NEW_OBJECTIVE_LABEL = "After-tax estate, less unfunded spending (taxes reported, not scored)"


def objective_row(result: dict, settings: dict) -> tuple[str, str]:
    """(label, value) describing what a run optimized.

    Runs carry an ``objective`` id from October 2026 on. Older runs scored
    −PV(taxes) + estate_weight·PV(estate) and keep their stored priority label;
    the presence of ``estate_weight`` in a snapshot proves nothing, since newer
    plans still store it.
    """
    if result.get("objective"):
        return "Objective", NEW_OBJECTIVE_LABEL
    ew = settings.get("estate_weight")
    weight = 1.0 if ew is None else float(ew)
    return "Optimization priority", _PRIORITY.get(weight, f"Estate weight {ew}")


def tax_tables_label(result: dict) -> str:
    """How the run's tax tables were built. Runs saved before projection
    existed carry no ``tax_tables`` and froze every table at its last
    published year."""
    tt = result.get("tax_tables")
    if not tt:
        return "Frozen at the last published year"
    rate = float(tt.get("indexation_rate") or 0) * 100
    states = ", ".join(tt.get("state_indexed") or []) or "none"
    return (
        f"Federal and IRMAA published through {tt['federal_published_through']}, "
        f"state through {tt['state_published_through']}; later years indexed at "
        f"{rate:.1f}% (state: {states} only; IRMAA premiums not projected)"
    )
