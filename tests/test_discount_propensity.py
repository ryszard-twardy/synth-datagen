from __future__ import annotations

import numpy as np

from synth_datagen.discounts import (
    DISCOUNT_CAP,
    DISCOUNT_PROPENSITY_BANDS,
    beta_parameters_for_propensity,
    build_discount_rng,
    build_propensity_lookup,
    sample_discount,
)


def test_beta_parameters_follow_requested_formula() -> None:
    alpha, beta = beta_parameters_for_propensity(0.20)
    assert alpha == 2.0
    assert beta == 8.0


def test_propensity_lookup_stays_inside_value_tier_bands() -> None:
    lookup = build_propensity_lookup(
        {
            "CUST-003": "low",
            "CUST-001": "high",
            "CUST-002": "mid",
        },
        base_seed=42,
    )
    assert DISCOUNT_PROPENSITY_BANDS["high"][0] <= lookup["CUST-001"] <= DISCOUNT_PROPENSITY_BANDS["high"][1]
    assert DISCOUNT_PROPENSITY_BANDS["mid"][0] <= lookup["CUST-002"] <= DISCOUNT_PROPENSITY_BANDS["mid"][1]
    assert DISCOUNT_PROPENSITY_BANDS["low"][0] <= lookup["CUST-003"] <= DISCOUNT_PROPENSITY_BANDS["low"][1]


def test_discount_rng_is_deterministic_for_same_seed() -> None:
    first = build_discount_rng(42).beta(2.0, 8.0, size=5)
    second = build_discount_rng(42).beta(2.0, 8.0, size=5)
    assert np.allclose(first, second)


def test_discount_cap_is_enforced() -> None:
    class StubRng:
        def beta(self, alpha: float, beta: float) -> float:
            return 0.99

    assert sample_discount(0.40, StubRng()) == DISCOUNT_CAP
