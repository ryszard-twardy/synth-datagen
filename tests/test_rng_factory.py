"""Tests for synth_datagen.rng — the single-source-of-truth RNG factory
introduced in Phase 2 to address audit findings P0-3 and P1-11.
"""

from __future__ import annotations

import numpy as np
import pytest

from synth_datagen.rng import SALT_REGISTRY, make_rng, register_salt


def test_master_concern_matches_legacy_default_rng():
    """For the legacy 'master' concern (salt=0), make_rng must produce the
    exact byte stream of np.random.default_rng(seed) — the backward-compat
    contract every classic generator depends on.
    """
    legacy = np.random.default_rng(42)
    factory = make_rng(42, "master")
    legacy_draws = legacy.integers(0, 1_000_000, size=1000)
    factory_draws = factory.integers(0, 1_000_000, size=1000)
    assert np.array_equal(legacy_draws, factory_draws)


def test_discounts_concern_matches_legacy_xor_mask():
    """Discounts pre-existed with XOR mask int.from_bytes(b'D15C0UNT', 'big').
    Migration must not shift the discount stream.
    """
    legacy_mask = int.from_bytes(b"D15C0UNT", "big")
    legacy = np.random.default_rng(seed=42 ^ legacy_mask)
    factory = make_rng(42, "discounts")
    assert np.array_equal(
        legacy.integers(0, 1_000_000, size=500),
        factory.integers(0, 1_000_000, size=500),
    )


def test_unknown_concern_raises_keyerror():
    """Unregistered concerns must fail loudly so the bug shows up at the
    offending commit, not later in a baseline-diff break."""
    with pytest.raises(KeyError, match="Unknown RNG concern"):
        make_rng(42, "this_concern_does_not_exist")


def test_concerns_produce_independent_streams():
    """Two registered concerns with the same base_seed must produce
    different draws — that's the whole point of stream isolation."""
    a = make_rng(42, "master").integers(0, 1_000_000, size=100)
    b = make_rng(42, "discounts").integers(0, 1_000_000, size=100)
    assert not np.array_equal(a, b)


def test_register_salt_rejects_conflicting_value():
    """Re-registering an existing concern with a different salt must
    raise — protects against accidental salt collisions."""
    with pytest.raises(ValueError, match="already registered"):
        register_salt("master", 0xDEADBEEF)


def test_register_salt_is_idempotent_with_same_value():
    """Re-registering the same value (e.g. on module reload) must be safe."""
    register_salt("master", 0)
    assert SALT_REGISTRY["master"] == 0


def test_saas_v3_salt_registered() -> None:
    assert SALT_REGISTRY["saas_v3"] == 0x5AA50000


def test_saas_v3_make_rng_independent_of_master() -> None:
    master = make_rng(42, "master")
    saas = make_rng(42, "saas_v3")
    # First five draws must differ — proves stream isolation.
    assert list(master.integers(0, 1_000_000, size=5)) != list(
        saas.integers(0, 1_000_000, size=5)
    )
