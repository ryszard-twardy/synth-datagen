"""Hypothesis property tests for fintech scenario invariants.

The card-expiry test here is the fuzzed companion to the explicit Feb-29
regression test in tests/test_fintech_leap_day.py — together they catch any
future date-arithmetic regression at both ends (specific anchor years and
random seeds)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.property._helpers import generate_scenario

_PROP_SETTINGS = settings(
    max_examples=3,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
_SEED_STRATEGY = st.integers(min_value=0, max_value=2**31 - 1)


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_fintech_same_seed_reproducible(seed: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        a = generate_scenario("fintech", seed, output_dir=Path(tmp) / "a")
        b = generate_scenario("fintech", seed, output_dir=Path(tmp) / "b")
    assert set(a) == set(b)
    for name in a:
        num_a = a[name].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b[name].select_dtypes(include=["number"]).reset_index(drop=True)
        assert num_a.equals(num_b), f"fintech/{name}: numeric columns differ"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_fintech_schema_stable(seed: int) -> None:
    expected = {
        "cards": [
            "card_id",
            "account_id",
            "card_type",
            "network",
            "last4",
            "issue_date",
            "expiry_date",
            "is_active",
            "spend_limit",
        ],
        "loans": [
            "loan_id",
            "customer_id",
            "loan_type",
            "principal",
            "interest_rate",
            "term_months",
            "monthly_payment",
            "outstanding",
            "status",
            "disbursed_at",
            "due_date",
            "currency",
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("fintech", seed, output_dir=tmp)
    for name, cols in expected.items():
        assert list(out[name].columns) == cols, f"fintech/{name} columns drifted"


@pytest.mark.parametrize("seed_pair", [(42, 99), (0, 1)])
def test_fintech_different_seeds_differ(seed_pair: tuple[int, int]) -> None:
    s1, s2 = seed_pair
    with tempfile.TemporaryDirectory() as tmp:
        out1 = generate_scenario("fintech", s1, output_dir=Path(tmp) / "a")
        out2 = generate_scenario("fintech", s2, output_dir=Path(tmp) / "b")
    bal1 = out1["accounts"]["balance"].to_numpy()
    bal2 = out2["accounts"]["balance"].to_numpy()
    assert not (bal1 == bal2).all(), f"seeds {s1}/{s2} produced identical balances"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_fintech_card_expiry_after_issue(seed: int) -> None:
    """Every card's expiry_date strictly follows its issue_date.

    Fuzzed companion to test_fintech_leap_day.py — catches any regression
    in ``_advance_years_safe`` that would set expiry == issue or earlier."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("fintech", seed, output_dir=tmp)
    cards = out["cards"]
    bad = cards[cards["expiry_date"] <= cards["issue_date"]]
    assert bad.empty, (
        f"{len(bad)} cards have expiry_date <= issue_date "
        f"(seed={seed}): {bad.head(3).to_dict('records')}"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_fintech_loan_outstanding_within_principal(seed: int) -> None:
    """Outstanding balance never exceeds principal — basic loan-arithmetic
    sanity check."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("fintech", seed, output_dir=tmp)
    loans = out["loans"]
    bad = loans[loans["outstanding"] > loans["principal"] + 0.01]
    assert bad.empty, (
        f"{len(bad)} loans have outstanding > principal (seed={seed})"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_fintech_account_customer_fk_integrity(seed: int) -> None:
    """Every account.customer_id resolves to an existing customer."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("fintech", seed, output_dir=tmp)
    customers = set(out["customers"]["customer_id"])
    account_customers = set(out["accounts"]["customer_id"])
    assert account_customers <= customers, "orphan customer_id in accounts"
