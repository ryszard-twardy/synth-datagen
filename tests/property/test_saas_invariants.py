"""Hypothesis property tests for SaaS scenario invariants."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.property._helpers import generate_scenario

_PROP_SETTINGS = settings(
    max_examples=5,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
_SEED_STRATEGY = st.integers(min_value=0, max_value=2**31 - 1)


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_saas_same_seed_reproducible(seed: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        a = generate_scenario("saas", seed, output_dir=Path(tmp) / "a")
        b = generate_scenario("saas", seed, output_dir=Path(tmp) / "b")
    assert set(a) == set(b)
    for name in a:
        num_a = a[name].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b[name].select_dtypes(include=["number"]).reset_index(drop=True)
        assert num_a.equals(num_b), f"saas/{name}: numeric columns differ"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_saas_schema_stable(seed: int) -> None:
    expected = {
        "accounts": [
            "account_id",
            "company_name",
            "domain",
            "industry",
            "employee_count",
            "country",
            "created_at",
            "mrr",
        ],
        "subscriptions": [
            "sub_id",
            "account_id",
            "plan",
            "status",
            "mrr",
            "started_at",
            "ended_at",
            "billing_cycle",
        ],
        "invoices": [
            "account_id",
            "sub_id",
            "amount",
            "currency",
            "status",
            "issued_at",
            "due_at",
            "paid_at",
            "invoice_id",
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("saas", seed, output_dir=tmp)
    for name, cols in expected.items():
        assert list(out[name].columns) == cols, f"saas/{name} columns drifted"


@pytest.mark.parametrize("seed_pair", [(42, 99), (0, 1)])
def test_saas_different_seeds_differ(seed_pair: tuple[int, int]) -> None:
    s1, s2 = seed_pair
    with tempfile.TemporaryDirectory() as tmp:
        out1 = generate_scenario("saas", s1, output_dir=Path(tmp) / "a")
        out2 = generate_scenario("saas", s2, output_dir=Path(tmp) / "b")
    mrr1 = out1["accounts"]["mrr"].to_numpy()
    mrr2 = out2["accounts"]["mrr"].to_numpy()
    assert not (mrr1 == mrr2).all(), f"seeds {s1}/{s2} produced identical MRRs"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_saas_no_negative_mrr_or_invoice_amounts(seed: int) -> None:
    """MRR and invoice amounts must always be non-negative."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("saas", seed, output_dir=tmp)
    assert (out["accounts"]["mrr"] >= 0).all(), "negative account MRR"
    assert (out["subscriptions"]["mrr"] >= 0).all(), "negative subscription MRR"
    assert (out["invoices"]["amount"] >= 0).all(), "negative invoice amount"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_saas_user_account_fk_integrity(seed: int) -> None:
    """Every user.account_id resolves to an existing account."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("saas", seed, output_dir=tmp)
    accounts = set(out["accounts"]["account_id"])
    user_accounts = set(out["users"]["account_id"])
    assert user_accounts <= accounts, "orphan account_id in users"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_saas_subscription_dates_consistent(seed: int) -> None:
    """ended_at >= started_at when both are present."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("saas", seed, output_dir=tmp)
    subs = out["subscriptions"]
    closed = subs.dropna(subset=["ended_at"])
    if len(closed) == 0:
        return  # nothing to assert
    bad = closed[closed["ended_at"] < closed["started_at"]]
    assert bad.empty, f"{len(bad)} subscriptions ended before they started"
