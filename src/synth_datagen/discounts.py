"""
Shared discount propensity helpers for retail workflows.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .rng import SALT_REGISTRY, make_rng


DISCOUNT_ALPHA = 2.0
DISCOUNT_CAP = 0.55
# Kept as a public alias for any historical caller that imported the mask
# directly. The authoritative value lives in synth_datagen.rng.SALT_REGISTRY.
DISCOUNT_RNG_XOR_MASK = SALT_REGISTRY["discounts"]

DISCOUNT_PROPENSITY_BANDS: dict[str, tuple[float, float]] = {
    "high": (0.02, 0.15),
    "mid": (0.15, 0.30),
    "low": (0.25, 0.50),
}


def build_discount_rng(base_seed: int) -> np.random.Generator:
    return make_rng(int(base_seed), "discounts")


def beta_parameters_for_propensity(propensity: float) -> tuple[float, float]:
    bounded = float(np.clip(propensity, 1e-6, 0.999999))
    beta = (DISCOUNT_ALPHA / bounded) - DISCOUNT_ALPHA
    return DISCOUNT_ALPHA, beta


def sample_discount_propensity(tier: str, rng: np.random.Generator) -> float:
    band_min, band_max = DISCOUNT_PROPENSITY_BANDS[tier]
    return float(rng.uniform(band_min, band_max))


def sample_discount(propensity: float, rng: np.random.Generator) -> float:
    alpha, beta = beta_parameters_for_propensity(propensity)
    return float(min(rng.beta(alpha, beta), DISCOUNT_CAP))


def build_propensity_lookup(
    value_tier_by_customer_id: Mapping[str, str],
    *,
    base_seed: int,
) -> dict[str, float]:
    discount_rng = build_discount_rng(base_seed)
    propensities: dict[str, float] = {}
    for customer_id in sorted(
        str(customer_id) for customer_id in value_tier_by_customer_id
    ):
        tier = str(value_tier_by_customer_id[customer_id])
        propensities[customer_id] = sample_discount_propensity(tier, discount_rng)
    return propensities
