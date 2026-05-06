"""Hypothesis property tests for the Kupferkanne RFM scenario.

The full Kupferkanne config generates 15_000 customers across 39 months which
takes ~70s per build — far too slow for fuzzed property tests. This module
loads the canonical YAML config and shrinks it in-place to 200 customers
across a 2-month window (~1s per build), which keeps property tests under
~10s each while still exercising the full clean-frames pipeline.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from synth_datagen.kupferkanne_rfm import build_clean_kupferkanne_frames
from synth_datagen.kupferkanne_rfm_config import load_kupferkanne_rfm_config

_PROP_SETTINGS = settings(
    max_examples=5,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
_SEED_STRATEGY = st.integers(min_value=0, max_value=2**31 - 1)


def _make_small_config() -> Any:
    """Load the canonical Kupferkanne config and shrink it for property tests.

    Each test calls this so the underlying config object is fresh and the
    in-place mutations don't bleed across examples / tests.
    """
    config = load_kupferkanne_rfm_config(Path("configs/kupferkanne_rfm_v3.yaml"))
    # Deep-copy in case downstream code mutates the config during build.
    config = copy.deepcopy(config)
    config.customers.target_total_customers = 200
    config.period.end_date = date(2023, 2, 28)
    return config


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_kupferkanne_same_seed_reproducible(seed: int) -> None:
    """Same seed -> identical clean_lines numeric columns."""
    a = build_clean_kupferkanne_frames(_make_small_config(), seed=seed)
    b = build_clean_kupferkanne_frames(_make_small_config(), seed=seed)
    cols = ["Quantity", "UnitPrice", "UnitCost", "LineNetAmount"]
    pa = a["clean_lines"][cols].reset_index(drop=True)
    pb = b["clean_lines"][cols].reset_index(drop=True)
    assert pa.equals(pb), "clean_lines numeric columns differ for the same seed"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_kupferkanne_dim_customers_columns_stable(seed: int) -> None:
    """dim_customers exposes the canonical 12-column shape regardless of seed."""
    expected = [
        "CustomerID",
        "signup_date",
        "Country",
        "customer_archetype",
        "churn_end_month",
        "first_name",
        "last_name",
        "email",
        "phone",
        "state",
        "city",
        "address",
    ]
    out = build_clean_kupferkanne_frames(_make_small_config(), seed=seed)
    assert list(out["dim_customers"].columns) == expected


@pytest.mark.parametrize("seed_pair", [(42, 99), (0, 1)])
def test_kupferkanne_different_seeds_differ(seed_pair: tuple[int, int]) -> None:
    s1, s2 = seed_pair
    out1 = build_clean_kupferkanne_frames(_make_small_config(), seed=s1)
    out2 = build_clean_kupferkanne_frames(_make_small_config(), seed=s2)
    # Order date sequences cannot be identical for distinct seeds.
    dates1 = out1["clean_lines"]["OrderDate"].astype(str).to_numpy()
    dates2 = out2["clean_lines"]["OrderDate"].astype(str).to_numpy()
    if len(dates1) != len(dates2):
        return  # row count alone proves they differ
    assert not (dates1 == dates2).all(), (
        f"seeds {s1}/{s2} produced identical order-date sequences"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_kupferkanne_no_negative_quantities_or_amounts(seed: int) -> None:
    """Quantity > 0, UnitPrice > 0, LineNetAmount >= 0 on every clean line."""
    out = build_clean_kupferkanne_frames(_make_small_config(), seed=seed)
    lines = out["clean_lines"]
    assert (lines["Quantity"] > 0).all(), "non-positive Quantity"
    assert (lines["UnitPrice"] > 0).all(), "non-positive UnitPrice"
    assert (lines["UnitCost"] > 0).all(), "non-positive UnitCost"
    assert (lines["LineNetAmount"] >= 0).all(), "negative LineNetAmount"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_kupferkanne_orders_have_at_least_one_line_each(seed: int) -> None:
    """Every OrderID in fact_orders appears at least once in clean_lines."""
    out = build_clean_kupferkanne_frames(_make_small_config(), seed=seed)
    order_ids_orders = set(out["fact_orders"]["OrderID"])
    order_ids_lines = set(out["clean_lines"]["OrderID"])
    missing = order_ids_orders - order_ids_lines
    assert not missing, f"{len(missing)} fact_orders rows have no clean_lines"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_kupferkanne_dim_customers_email_unique(seed: int) -> None:
    """No duplicate emails in dim_customers — basic PII uniqueness invariant."""
    out = build_clean_kupferkanne_frames(_make_small_config(), seed=seed)
    emails = out["dim_customers"]["email"]
    assert emails.is_unique, "duplicate emails in dim_customers"


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_kupferkanne_clean_lines_customer_fk_resolves(seed: int) -> None:
    """Every clean_lines.CustomerID resolves to a dim_customers row."""
    out = build_clean_kupferkanne_frames(_make_small_config(), seed=seed)
    customer_ids = set(out["dim_customers"]["CustomerID"])
    line_customers = set(out["clean_lines"]["CustomerID"])
    assert line_customers <= customer_ids, "orphan CustomerID in clean_lines"
