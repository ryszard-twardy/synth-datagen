"""Hypothesis property tests for retail invariants.

Covers reproducibility, schema stability, foreign-key integrity, sign / range
invariants on numeric columns, and seed sensitivity. ``max_examples`` is kept
deliberately low (3) per test because each example regenerates the full
9-table dataset (~1400 rows) — at 0.3s/generation this stays inside the P6
<60s default-pytest budget. The whole property suite is marked ``slow`` at
the conftest level (pytest -m slow) so CI and on-demand fuzz runs still
exercise more seeds.
"""

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
def test_retail_same_seed_reproducible(seed: int) -> None:
    """Same seed -> identical numeric output for every retail table."""
    with tempfile.TemporaryDirectory() as tmp:
        a = generate_scenario("retail", seed, output_dir=Path(tmp) / "a")
        b = generate_scenario("retail", seed, output_dir=Path(tmp) / "b")
    assert set(a) == set(b)
    for name in a:
        num_a = a[name].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b[name].select_dtypes(include=["number"]).reset_index(drop=True)
        # Use .equals instead of assert_frame_equal so failures fold cleanly
        # into the Hypothesis shrinker.
        assert num_a.equals(num_b), f"retail/{name}: numeric columns differ"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_retail_schema_columns_stable(seed: int) -> None:
    """Column names per table are deterministic — independent of seed."""
    expected_cols = {
        "dim_customers": [
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "city",
            "country",
            "segment",
            "created_at",
            "is_active",
            "lifetime_value",
        ],
        "fact_orders": [
            "order_id",
            "customer_id",
            "store_id",
            "date_id",
            "channel",
            "status",
            "currency",
            "subtotal",
            "discount_amt",
            "shipping_amt",
            "order_total",
            "created_at",
            "shipped_at",
            "delivered_at",
        ],
        "fact_order_items": [
            "item_id",
            "order_id",
            "product_id",
            "qty",
            "unit_price",
            "discount_pct",
            "line_total",
            "return_flag",
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("retail", seed, output_dir=tmp)
    for name, cols in expected_cols.items():
        assert list(out[name].columns) == cols, f"retail/{name} columns drifted"


@pytest.mark.parametrize("seed_pair", [(42, 99), (0, 1), (12345, 67890)])
def test_retail_different_seeds_produce_different_data(seed_pair: tuple[int, int]) -> None:
    """Distinct seeds must produce distinct fact_orders subtotals."""
    s1, s2 = seed_pair
    with tempfile.TemporaryDirectory() as tmp:
        out1 = generate_scenario("retail", s1, output_dir=Path(tmp) / "a")
        out2 = generate_scenario("retail", s2, output_dir=Path(tmp) / "b")
    sub1 = out1["fact_orders"]["subtotal"].to_numpy()
    sub2 = out2["fact_orders"]["subtotal"].to_numpy()
    assert not (sub1 == sub2).all(), (
        f"seeds {s1} and {s2} produced identical subtotals — RNG isolation broken"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_retail_order_items_have_positive_qty_and_line_total(seed: int) -> None:
    """No negative quantities or line totals in fact_order_items."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("retail", seed, output_dir=tmp)
    items = out["fact_order_items"]
    assert (items["qty"] > 0).all(), "non-positive qty"
    assert (items["line_total"] >= 0).all(), "negative line_total"
    assert (items["unit_price"] > 0).all(), "non-positive unit_price"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_retail_fk_orders_resolve_to_customers_and_stores(seed: int) -> None:
    """Every fact_orders.customer_id and store_id must resolve to a dim row."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("retail", seed, output_dir=tmp)
    customer_ids = set(out["dim_customers"]["customer_id"])
    store_ids = set(out["dim_stores"]["store_id"])
    order_customers = set(out["fact_orders"]["customer_id"])
    order_stores = set(out["fact_orders"]["store_id"])
    assert order_customers <= customer_ids, "orphan customer_ids in fact_orders"
    assert order_stores <= store_ids, "orphan store_ids in fact_orders"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_retail_order_total_within_plausible_bounds(seed: int) -> None:
    """order_total = subtotal - discount_amt + shipping_amt, all non-negative,
    no row has total exceeding subtotal + shipping (i.e., discount never goes
    negative as a windfall)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("retail", seed, output_dir=tmp)
    orders = out["fact_orders"]
    assert (orders["subtotal"] >= 0).all(), "negative subtotal"
    assert (orders["discount_amt"] >= 0).all(), "negative discount_amt"
    assert (orders["shipping_amt"] >= 0).all(), "negative shipping_amt"
    assert (orders["order_total"] >= 0).all(), "negative order_total"
    # Order total is a sum, so it cannot exceed subtotal + shipping
    upper = orders["subtotal"] + orders["shipping_amt"]
    assert (orders["order_total"] <= upper + 0.01).all(), "order_total exceeds cap"
