from decimal import Decimal

from src.data.tax_rules.irmaa import IRMAA


def test_2025_first_threshold_and_standard_premium():
    y = IRMAA[2025]
    assert y.part_b_standard == Decimal("185.00")
    assert y.tiers["single"][0].magi_upper == Decimal("106000")
    assert y.tiers["joint"][0].magi_upper == Decimal("212000")
    assert y.tiers["single"][0].part_b_monthly == y.part_b_standard  # tier 0 = no surcharge


def test_tiers_ascend():
    for year in IRMAA:
        for status in ("single", "joint"):
            uppers = [t.magi_upper for t in IRMAA[year].tiers[status] if t.magi_upper]
            assert uppers == sorted(uppers)
            assert IRMAA[year].tiers[status][-1].magi_upper is None


def test_2026_standard_premium_and_first_threshold():
    y = IRMAA[2026]
    assert y.part_b_standard == Decimal("202.90")
    assert y.tiers["single"][0].magi_upper == Decimal("109000")
    assert y.tiers["joint"][0].magi_upper == Decimal("218000")
    assert y.tiers["single"][0].part_b_monthly == y.part_b_standard


def test_2026_top_tier():
    y = IRMAA[2026]
    assert y.tiers["single"][-1].magi_upper is None
    assert y.tiers["single"][-1].part_b_monthly == Decimal("689.90")
    assert y.tiers["single"][-1].part_d_monthly == Decimal("91.00")
    assert y.tiers["joint"][-1].magi_upper is None
    assert y.tiers["joint"][-1].part_b_monthly == Decimal("689.90")


def test_2026_tier_count():
    y = IRMAA[2026]
    assert len(y.tiers["single"]) == 6
    assert len(y.tiers["joint"]) == 6


def test_2026_part_d_surcharges():
    y = IRMAA[2026]
    single = y.tiers["single"]
    assert single[0].part_d_monthly == Decimal("0")
    assert single[1].part_d_monthly == Decimal("14.50")
    assert single[2].part_d_monthly == Decimal("37.50")
    assert single[3].part_d_monthly == Decimal("60.40")
    assert single[4].part_d_monthly == Decimal("83.30")
    assert single[5].part_d_monthly == Decimal("91.00")


def test_no_verify_flag_in_sources():
    for year, y in IRMAA.items():
        assert "VERIFY" not in y.source, (
            f"IRMAA[{year}].source still contains VERIFY flag: {y.source!r}"
        )
