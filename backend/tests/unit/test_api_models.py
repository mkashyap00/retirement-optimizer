"""
TDD tests for API request/response Pydantic v2 models.
RED phase: write tests before implementation exists.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# HouseholdIn
# ---------------------------------------------------------------------------


class TestHouseholdIn:
    def test_joint_without_spouse_birthdate_raises(self):
        """Filing status joint requires spouse_birth_date."""
        from src.api.models import HouseholdIn

        with pytest.raises(ValidationError, match="spouse_birth_date"):
            HouseholdIn(
                filing_status="joint",
                self_birth_date=date(1960, 1, 1),
                spouse_birth_date=None,
                state="CA",
            )

    def test_single_without_spouse_birthdate_ok(self):
        """Single filer with no spouse_birth_date is valid."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="CA",
        )
        assert h.filing_status == "single"
        assert h.spouse_birth_date is None

    def test_joint_with_spouse_birthdate_ok(self):
        """Joint filer with spouse_birth_date is valid."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="joint",
            self_birth_date=date(1960, 1, 1),
            spouse_birth_date=date(1963, 5, 15),
            state="NY",
        )
        assert h.filing_status == "joint"
        assert h.spouse_birth_date == date(1963, 5, 15)

    def test_state_must_be_two_uppercase_letters(self):
        """State must be exactly 2 uppercase letters."""
        from src.api.models import HouseholdIn

        with pytest.raises(ValidationError):
            HouseholdIn(
                filing_status="single",
                self_birth_date=date(1960, 1, 1),
                state="California",
            )

    def test_state_lowercase_raises(self):
        """Lowercase state code raises ValidationError."""
        from src.api.models import HouseholdIn

        with pytest.raises(ValidationError):
            HouseholdIn(
                filing_status="single",
                self_birth_date=date(1960, 1, 1),
                state="ca",
            )

    def test_state_two_uppercase_ok(self):
        """Two uppercase letters is a valid state code."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="TX",
        )
        assert h.state == "TX"

    # --- nickname validator ---

    def test_nickname_none_by_default(self):
        """When nickname is omitted it defaults to None."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="CA",
        )
        assert h.nickname is None

    def test_nickname_valid_roundtrip(self):
        """A valid nickname is stored as-is (stripped)."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="CA",
            nickname="Retire at 65",
        )
        assert h.nickname == "Retire at 65"

    def test_nickname_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="CA",
            nickname="  My Plan  ",
        )
        assert h.nickname == "My Plan"

    def test_nickname_blank_becomes_none(self):
        """A whitespace-only nickname normalises to None."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="CA",
            nickname="   ",
        )
        assert h.nickname is None

    def test_nickname_61_chars_raises(self):
        """A nickname longer than 60 characters raises ValidationError."""
        from src.api.models import HouseholdIn

        long_name = "a" * 61
        with pytest.raises(ValidationError, match="60"):
            HouseholdIn(
                filing_status="single",
                self_birth_date=date(1960, 1, 1),
                state="CA",
                nickname=long_name,
            )

    def test_nickname_exactly_60_chars_ok(self):
        """A nickname of exactly 60 characters is valid."""
        from src.api.models import HouseholdIn

        name_60 = "b" * 60
        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="CA",
            nickname=name_60,
        )
        assert h.nickname == name_60

    def test_death_age_within_bounds_ok(self):
        """A death age within 40-120 is accepted."""
        from src.api.models import HouseholdIn

        h = HouseholdIn(
            filing_status="single",
            self_birth_date=date(1960, 1, 1),
            state="CA",
            self_death_age=95,
        )
        assert h.self_death_age == 95

    def test_death_age_too_high_raises(self):
        """A death age above 120 raises ValidationError."""
        from src.api.models import HouseholdIn

        with pytest.raises(ValidationError, match="between 40 and 120"):
            HouseholdIn(
                filing_status="single",
                self_birth_date=date(1960, 1, 1),
                state="CA",
                self_death_age=150,
            )

    def test_death_age_too_low_raises(self):
        """A death age below 40 raises ValidationError."""
        from src.api.models import HouseholdIn

        with pytest.raises(ValidationError, match="between 40 and 120"):
            HouseholdIn(
                filing_status="single",
                self_birth_date=date(1960, 1, 1),
                state="CA",
                self_death_age=30,
            )

    def test_spouse_death_age_without_spouse_raises(self):
        """spouse_death_age without a spouse birth date raises ValidationError."""
        from src.api.models import HouseholdIn

        with pytest.raises(ValidationError, match="spouse_death_age requires"):
            HouseholdIn(
                filing_status="single",
                self_birth_date=date(1960, 1, 1),
                state="CA",
                spouse_death_age=90,
            )


# ---------------------------------------------------------------------------
# AccountIn
# ---------------------------------------------------------------------------


class TestAccountIn:
    def test_taxable_without_basis_raises(self):
        """Taxable account without basis raises ValidationError."""
        from src.api.models import AccountIn

        with pytest.raises(ValidationError, match="basis"):
            AccountIn(
                account_type="taxable",
                owner="self",
                balance=Decimal("50000"),
                basis=None,
            )

    def test_taxable_with_basis_ok(self):
        """Taxable account with basis is valid."""
        from src.api.models import AccountIn

        a = AccountIn(
            account_type="taxable",
            owner="self",
            balance=Decimal("50000"),
            basis=Decimal("40000"),
        )
        assert a.basis == Decimal("40000")

    def test_a_taxable_account_at_a_loss_is_accepted(self):
        """Basis above market value is an ordinary unrealized loss -- the
        portfolio uploader already accepts one -- not an invalid state."""
        from src.api.models import AccountIn

        a = AccountIn(
            account_type="taxable",
            owner="self",
            balance=Decimal("30000"),
            basis=Decimal("50000"),
        )
        assert a.basis == Decimal("50000")

    def test_basis_negative_raises(self):
        """Negative basis raises ValidationError."""
        from src.api.models import AccountIn

        with pytest.raises(ValidationError, match="basis"):
            AccountIn(
                account_type="taxable",
                owner="self",
                balance=Decimal("30000"),
                basis=Decimal("-1"),
            )

    def test_traditional_without_basis_ok(self):
        """Traditional account without basis is valid (optional Form 8606)."""
        from src.api.models import AccountIn

        a = AccountIn(
            account_type="traditional",
            owner="self",
            balance=Decimal("100000"),
        )
        assert a.basis is None

    def test_traditional_with_valid_basis_ok(self):
        """Traditional account with basis <= balance is valid."""
        from src.api.models import AccountIn

        a = AccountIn(
            account_type="traditional",
            owner="self",
            balance=Decimal("100000"),
            basis=Decimal("20000"),
        )
        assert a.basis == Decimal("20000")

    def test_traditional_basis_exceeds_balance_raises(self):
        """Traditional basis > balance raises ValidationError."""
        from src.api.models import AccountIn

        with pytest.raises(ValidationError, match="basis"):
            AccountIn(
                account_type="traditional",
                owner="self",
                balance=Decimal("50000"),
                basis=Decimal("60000"),
            )

    def test_roth_no_basis_ok(self):
        """Roth account without basis is valid."""
        from src.api.models import AccountIn

        a = AccountIn(
            account_type="roth",
            owner="self",
            balance=Decimal("80000"),
        )
        assert a.account_type == "roth"
        assert a.basis is None


# ---------------------------------------------------------------------------
# IncomeIn
# ---------------------------------------------------------------------------


class TestIncomeIn:
    def test_happy_path(self):
        """IncomeIn constructs with required fields."""
        from src.api.models import IncomeIn

        inc = IncomeIn(
            category="salary",
            owner="self",
            amount=Decimal("80000"),
        )
        assert inc.category == "salary"
        assert inc.start_year is None

    def test_with_year_range(self):
        """IncomeIn accepts start_year and end_year."""
        from src.api.models import IncomeIn

        inc = IncomeIn(
            category="pension",
            owner="spouse",
            amount=Decimal("24000"),
            start_year=2030,
            end_year=2050,
        )
        assert inc.start_year == 2030
        assert inc.end_year == 2050

    def test_invalid_category_raises(self):
        """Unknown category raises ValidationError."""
        from src.api.models import IncomeIn

        with pytest.raises(ValidationError):
            IncomeIn(category="gambling", owner="self", amount=Decimal("1000"))

    def test_joint_owner_ok(self):
        """Income from a jointly-held source (e.g. brokerage dividends) is valid."""
        from src.api.models import IncomeIn

        inc = IncomeIn(
            category="qualified_dividend",
            owner="joint",
            amount=Decimal("12000"),
        )
        assert inc.owner == "joint"


# ---------------------------------------------------------------------------
# SettingsIn
# ---------------------------------------------------------------------------


class TestSettingsIn:
    def test_claim_age_below_62_raises(self):
        """SS claim age below 62 raises ValidationError."""
        from src.api.models import SettingsIn

        with pytest.raises(ValidationError, match="claim_age"):
            SettingsIn(
                required_spending=Decimal("60000"),
                ss_pia_self=Decimal("2000"),
                ss_claim_age_self=61,  # invalid
            )

    def test_claim_age_above_70_raises(self):
        """SS claim age above 70 raises ValidationError."""
        from src.api.models import SettingsIn

        with pytest.raises(ValidationError, match="claim_age"):
            SettingsIn(
                required_spending=Decimal("60000"),
                ss_pia_self=Decimal("2000"),
                ss_claim_age_self=71,  # invalid
            )

    def test_spouse_claim_age_constrained(self):
        """Spouse SS claim age must also be 62-70."""
        from src.api.models import SettingsIn

        with pytest.raises(ValidationError, match="claim_age"):
            SettingsIn(
                required_spending=Decimal("60000"),
                ss_pia_self=Decimal("2000"),
                ss_pia_spouse=Decimal("1500"),
                ss_claim_age_spouse=60,
            )

    def test_happy_path_defaults(self):
        """SettingsIn with minimal required fields uses defaults."""
        from src.api.models import SettingsIn

        s = SettingsIn(
            required_spending=Decimal("60000"),
            ss_pia_self=Decimal("2000"),
        )
        assert s.inflation == Decimal("0.03")
        assert s.nominal_return == Decimal("0.06")
        assert s.ss_claim_age_self == 67

    def test_valid_claim_ages_62_to_70(self):
        """Claim ages 62..70 inclusive are valid."""
        from src.api.models import SettingsIn

        for age in (62, 65, 67, 70):
            s = SettingsIn(
                required_spending=Decimal("60000"),
                ss_pia_self=Decimal("2000"),
                ss_claim_age_self=age,
            )
            assert s.ss_claim_age_self == age


# ---------------------------------------------------------------------------
# ConstraintsIn
# ---------------------------------------------------------------------------


class TestConstraintsIn:
    def test_defaults(self):
        """ConstraintsIn constructs with defaults."""
        from src.api.models import ConstraintsIn

        c = ConstraintsIn()
        assert c.irmaa_policy == "soft"
        assert c.conversion_window == "anytime"
        assert c.preserve_taxable is False

    def test_invalid_irmaa_policy_raises(self):
        """Unknown irmaa_policy raises ValidationError."""
        from src.api.models import ConstraintsIn

        with pytest.raises(ValidationError):
            ConstraintsIn(irmaa_policy="maybe")


# ---------------------------------------------------------------------------
# HouseholdPayload (composite)
# ---------------------------------------------------------------------------


class TestHouseholdPayload:
    def _valid_payload_data(self):
        return {
            "household": {
                "filing_status": "joint",
                "self_birth_date": "1960-03-15",
                "spouse_birth_date": "1963-07-22",
                "state": "CA",
            },
            "accounts": [
                {
                    "account_type": "taxable",
                    "owner": "self",
                    "balance": "100000",
                    "basis": "80000",
                },
                {
                    "account_type": "traditional",
                    "owner": "self",
                    "balance": "250000",
                },
                {
                    "account_type": "roth",
                    "owner": "spouse",
                    "balance": "50000",
                },
            ],
            "income": [
                {
                    "category": "salary",
                    "owner": "self",
                    "amount": "120000",
                    "end_year": 2030,
                },
            ],
            "settings": {
                "required_spending": "80000",
                "ss_pia_self": "2400",
                "ss_pia_spouse": "1200",
                "ss_claim_age_spouse": 66,
            },
        }

    def test_happy_path_constructs(self):
        """HouseholdPayload constructs from valid nested data."""
        from src.api.models import HouseholdPayload

        p = HouseholdPayload(**self._valid_payload_data())
        assert p.household.state == "CA"
        assert len(p.accounts) == 3
        assert len(p.income) == 1
        assert p.settings.ss_claim_age_self == 67
        assert p.constraints.irmaa_policy == "soft"

    def test_empty_income_list_default(self):
        """income defaults to empty list."""
        from src.api.models import HouseholdPayload

        data = self._valid_payload_data()
        del data["income"]
        p = HouseholdPayload(**data)
        assert p.income == []

    def test_nested_validation_propagates(self):
        """Nested model validation errors propagate through HouseholdPayload."""
        from src.api.models import HouseholdPayload

        data = self._valid_payload_data()
        data["household"]["filing_status"] = "joint"
        data["household"]["spouse_birth_date"] = None
        with pytest.raises(ValidationError):
            HouseholdPayload(**data)


# ---------------------------------------------------------------------------
# OptimizeRequest
# ---------------------------------------------------------------------------


class TestOptimizeRequest:
    def test_defaults(self):
        """OptimizeRequest has correct defaults."""
        from src.api.models import OptimizeRequest

        r = OptimizeRequest(household_id="abc-123")
        # Raised from 100 in the adaptive-staging change: only contenders
        # are carried to the full count, so the precision costs far less
        # than 3x, and 100 left the success probability at ~+/-9 points.
        assert r.monte_carlo_runs == 300

    def test_custom_runs(self):
        """OptimizeRequest accepts custom monte_carlo_runs."""
        from src.api.models import OptimizeRequest

        r = OptimizeRequest(household_id="abc-123", monte_carlo_runs=500)
        assert r.monte_carlo_runs == 500


# ---------------------------------------------------------------------------
# Invalid financial states are rejected at the API, not persisted
# ---------------------------------------------------------------------------


def _hh(**over):
    base = dict(filing_status="single", self_birth_date=date(1960, 1, 1), state="CA")
    base.update(over)
    return base


def _payload(**over):
    base = dict(
        household=_hh(),
        accounts=[dict(account_type="roth", owner="self", balance="1000")],
        income=[],
        settings=dict(required_spending="50000", ss_pia_self="0"),
    )
    base.update(over)
    return base


@pytest.mark.parametrize("model, fields", [
    ("AccountIn", dict(account_type="traditional", owner="self", balance="-1")),
    ("AccountIn", dict(account_type="taxable", owner="self", balance="-1", basis="0")),
    ("IncomeIn", dict(category="pension", owner="self", amount="-1")),
    ("IncomeIn", dict(category="pension", owner="self", amount="1000",
                      start_year=2030, end_year=2029)),
    ("SettingsIn", dict(required_spending="-1", ss_pia_self="0")),
    ("SettingsIn", dict(required_spending="0", ss_pia_self="0")),
    ("SettingsIn", dict(required_spending="1", ss_pia_self="-1")),
    ("SettingsIn", dict(required_spending="1", ss_pia_self="0", ss_pia_spouse="-1")),
    ("SettingsIn", dict(required_spending="1", ss_pia_self="0", inflation="2")),
    ("SettingsIn", dict(required_spending="1", ss_pia_self="0", nominal_return="-0.9")),
    ("ConstraintsIn", dict(marginal_rate_limit="1.5")),
    ("ConstraintsIn", dict(max_conversion_per_year="-1")),
    ("ConstraintsIn", dict(target_estate="-1")),
    ("HouseholdIn", _hh(state="ZZ")),
    ("OptimizeRequest", dict(household_id="x", monte_carlo_runs=-1)),
    ("OptimizeRequest", dict(household_id="x", monte_carlo_runs=1_000_000)),
])
def test_an_invalid_financial_state_is_rejected(model, fields):
    import src.api.models as models

    with pytest.raises(ValidationError):
        getattr(models, model)(**fields)


def test_district_of_columbia_is_a_supported_state():
    from src.api.models import HouseholdIn

    assert HouseholdIn(**_hh(state="DC")).state == "DC"


@pytest.mark.parametrize("over", [
    dict(accounts=[dict(account_type="roth", owner="spouse", balance="1000")]),
    dict(income=[dict(category="pension", owner="spouse", amount="1000")]),
])
def test_a_spouse_owned_item_needs_a_spouse(over):
    """With no spouse, a spouse-owned account or income has no owner's age
    for RMDs and no death to stop it at."""
    from src.api.models import HouseholdPayload

    with pytest.raises(ValidationError, match="spouse"):
        HouseholdPayload(**_payload(**over))


def test_a_compare_request_rejects_a_negative_run_count():
    from src.api.endpoints.compare import CompareRequest

    with pytest.raises(ValidationError):
        CompareRequest(household_id="x", monte_carlo_runs=-1)
