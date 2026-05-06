"""Hypothesis property tests for logistics scenario invariants."""

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
def test_logistics_same_seed_reproducible(seed: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        a = generate_scenario("logistics", seed, output_dir=Path(tmp) / "a")
        b = generate_scenario("logistics", seed, output_dir=Path(tmp) / "b")
    assert set(a) == set(b)
    for name in a:
        num_a = a[name].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b[name].select_dtypes(include=["number"]).reset_index(drop=True)
        assert num_a.equals(num_b), f"logistics/{name}: numeric columns differ"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_logistics_schema_stable(seed: int) -> None:
    expected = {
        "shipments": [
            "shipment_id",
            "carrier_id",
            "origin_wh",
            "dest_country",
            "status",
            "transport_mode",
            "incoterm",
            "shipped_at",
            "estimated_at",
            "delivered_at",
            "freight_cost",
        ],
        "inventory": [
            "inv_id",
            "warehouse_id",
            "product_id",
            "qty_on_hand",
            "qty_reserved",
            "last_updated",
            "reorder_point",
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("logistics", seed, output_dir=tmp)
    for name, cols in expected.items():
        assert list(out[name].columns) == cols, f"logistics/{name} columns drifted"


@pytest.mark.parametrize("seed_pair", [(42, 99), (0, 1)])
def test_logistics_different_seeds_differ(seed_pair: tuple[int, int]) -> None:
    s1, s2 = seed_pair
    with tempfile.TemporaryDirectory() as tmp:
        out1 = generate_scenario("logistics", s1, output_dir=Path(tmp) / "a")
        out2 = generate_scenario("logistics", s2, output_dir=Path(tmp) / "b")
    cost1 = out1["shipments"]["freight_cost"].to_numpy()
    cost2 = out2["shipments"]["freight_cost"].to_numpy()
    assert not (cost1 == cost2).all(), (
        f"seeds {s1}/{s2} produced identical freight costs"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_logistics_inventory_quantities_non_negative(seed: int) -> None:
    """qty_on_hand and qty_reserved must always be non-negative integers."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("logistics", seed, output_dir=tmp)
    inv = out["inventory"]
    assert (inv["qty_on_hand"] >= 0).all(), "negative qty_on_hand"
    assert (inv["qty_reserved"] >= 0).all(), "negative qty_reserved"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_logistics_shipment_items_have_positive_qty(seed: int) -> None:
    """No zero-or-negative quantities on any shipment line."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("logistics", seed, output_dir=tmp)
    items = out["shipment_items"]
    assert (items["qty"] > 0).all(), "non-positive shipment_items.qty"
    assert (items["unit_cost"] >= 0).all(), "negative unit_cost"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_logistics_shipment_carrier_fk_integrity(seed: int) -> None:
    """Every shipment.carrier_id resolves to an existing carrier."""
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_scenario("logistics", seed, output_dir=tmp)
    carriers = set(out["carriers"]["carrier_id"])
    shipment_carriers = set(out["shipments"]["carrier_id"])
    assert shipment_carriers <= carriers, "orphan carrier_id in shipments"
