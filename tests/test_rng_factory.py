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


# ---------------------------------------------------------------------------
# Phase 6 — Pharma salt registration (v0.3.0).
#
# The pharma scenario uses a single salt + .spawn(N) for sub-streams, mirroring
# the saas_v3 pattern from Phase 5. The literal value 0x5DDA50000 is locked
# (reads as "PHA50000" in hex; cf. SaaS 0x5AA50000). Adding a new salt MUST
# come with this regression guard so a typo in the literal surfaces here, not
# inside a Phase-7 baseline-diff break.
# ---------------------------------------------------------------------------


def test_pharma_salt_registered() -> None:
    """Pharma concern must be registered with the locked literal salt."""
    assert SALT_REGISTRY["pharma"] == 0x5DDA50000


def test_pharma_make_rng_does_not_raise() -> None:
    """make_rng(seed, 'pharma') must resolve via the existing factory.

    No new function is added; the registry entry is sufficient.
    """
    rng = make_rng(42, "pharma")
    # Smoke: produces a usable Generator.
    assert rng.integers(0, 100) >= 0


def test_pharma_make_rng_independent_of_master() -> None:
    """Stream isolation between pharma and master at the same base seed."""
    master_draws = list(make_rng(42, "master").integers(0, 1_000_000, size=5))
    pharma_draws = list(make_rng(42, "pharma").integers(0, 1_000_000, size=5))
    assert master_draws != pharma_draws


def test_pharma_make_rng_independent_of_saas_v3() -> None:
    """Stream isolation between the two scenario-level salts.

    Same base seed, different concern → different draws. Guards against
    accidentally re-using 0x5AA50000 for pharma.
    """
    saas_draws = list(make_rng(42, "saas_v3").integers(0, 1_000_000, size=5))
    pharma_draws = list(make_rng(42, "pharma").integers(0, 1_000_000, size=5))
    assert saas_draws != pharma_draws


def test_pharma_salt_distinct_from_other_registered_salts() -> None:
    """The pharma salt must collide with no other registered concern."""
    pharma_salt = SALT_REGISTRY["pharma"]
    others = {k: v for k, v in SALT_REGISTRY.items() if k != "pharma"}
    assert pharma_salt not in others.values(), (
        f"Pharma salt {pharma_salt:#x} collides with: "
        f"{[k for k, v in others.items() if v == pharma_salt]}"
    )
