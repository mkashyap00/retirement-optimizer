"""Display names for policy ids in the exports."""
from src.reports.policy_labels import policy_label


def test_limited_duration_rules_are_named_from_their_id():
    assert policy_label("fill_22_thru_2031") == "Fill the 22% bracket through 2031"


def test_fixed_ids_use_the_map_and_unknown_ids_pass_through():
    assert policy_label("fill_12_annual") == "Fill the 12% bracket every year"
    assert policy_label("mystery") == "mystery"


def test_level_dollar_rules_say_the_amount_is_a_maximum():
    assert policy_label("level_5pct_annual") == "Convert up to 5% of the starting IRA every year"
    assert policy_label("level_10pct_thru_2029") == (
        "Convert up to 10% of the starting IRA each year through 2029"
    )


def test_level_dollar_rules_name_their_amount_given_the_starting_balance():
    # The share is taken once, of the traditional balance at the start.
    assert (policy_label("level_5pct_thru_2029", 1_000_000)
            == "Convert up to $50,000 annually through 2029")
    assert policy_label("level_20pct_annual", 1_234_567) == "Convert up to $246,913 annually"
    # Other rules ignore the balance.
    assert policy_label("fill_22_thru_2031", 1_000_000) == "Fill the 22% bracket through 2031"
