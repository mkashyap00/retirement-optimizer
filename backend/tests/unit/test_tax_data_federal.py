from decimal import Decimal

from src.data.tax_rules.federal import FEDERAL


def test_2025_standard_deduction_post_obbba():
    fy = FEDERAL[2025]
    assert fy.standard_deduction["single"] == Decimal("15750")
    assert fy.standard_deduction["joint"] == Decimal("31500")


def test_2025_bracket_edges():
    single = FEDERAL[2025].brackets["single"]
    assert [b.upper for b in single][:3] == [Decimal("11925"), Decimal("48475"), Decimal("103350")]
    assert single[-1].upper is None and single[-1].rate == Decimal("0.37")
    joint = FEDERAL[2025].brackets["joint"]
    assert joint[2].upper == Decimal("206700") and joint[2].rate == Decimal("0.22")


def test_2025_ltcg_zero_bracket():
    assert FEDERAL[2025].ltcg_brackets["joint"][0].upper == Decimal("96700")
    assert FEDERAL[2025].ltcg_brackets["joint"][0].rate == Decimal("0")


def test_2025_senior_bonus():
    sb = FEDERAL[2025].senior_bonus
    assert sb.amount_per_person == Decimal("6000")
    assert sb.phaseout_start["joint"] == Decimal("150000")
    assert (sb.first_year, sb.last_year) == (2025, 2028)


def test_2026_exists_and_is_larger_than_2025():
    fy25, fy26 = FEDERAL[2025], FEDERAL[2026]
    assert fy26.standard_deduction["joint"] > fy25.standard_deduction["joint"]
    for status in ("single", "joint"):
        for b25, b26 in zip(fy25.brackets[status], fy26.brackets[status], strict=True):
            assert b25.rate == b26.rate
            if b25.upper is not None:
                assert b26.upper > b25.upper  # inflation adjustment


def test_2026_salt_cap_stepped_up():
    assert FEDERAL[2026].salt.cap["joint"] == Decimal("40400")
