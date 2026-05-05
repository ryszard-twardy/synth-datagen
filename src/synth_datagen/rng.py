"""Single-source-of-truth RNG factory for synth-datagen (audit P0-3).

Every random draw in the project should derive from ``make_rng(base_seed,
concern)``. The factory keeps streams isolated via XOR salts so that adding
a new concern in one scenario cannot shift another scenario's bytes.

## Salt convention

- ``"master"`` (salt ``0``) is the legacy concern used by every classic
  scenario generator (retail/saas/fintech/logistics) and by the kupferkanne
  generators. ``base_seed ^ 0 == base_seed`` so this is bit-identical to
  the historical ``np.random.default_rng(seed)`` calls — required for the
  Phase 2 backward-compat guarantee.
- ``"discounts"`` (salt ``int.from_bytes(b"D15C0UNT", "big")``) is the
  pre-existing salted stream used by retail discount propensity. Migrated
  to the factory verbatim.
- New concerns added in Phase 5/6 (SaaS sub-modes, Pharma) MUST register
  a distinct salt below before being used. Reusing an existing salt for a
  new concern is a bug.

## Why "register or raise"?

The previous fragile pattern (``np.random.default_rng(seed)`` everywhere)
made it impossible to add a new field without shifting downstream draws.
This factory rejects unknown concerns at call time so the failure surfaces
at the offending commit, not three commits later when a baseline diff
breaks for unrelated reasons.
"""

from __future__ import annotations

import numpy as np

# Pre-existing legacy salt — int.from_bytes(b"D15C0UNT", "big").
# Kept as the literal byte expression to make the lineage obvious.
_DISCOUNTS_SALT = int.from_bytes(b"D15C0UNT", "big")

SALT_REGISTRY: dict[str, int] = {
    "master": 0,
    "discounts": _DISCOUNTS_SALT,
}


def register_salt(concern: str, salt: int) -> None:
    """Add a new salted concern. Raises if the name is already taken with a
    different salt — re-registering the same value is allowed (idempotent
    for module reloads in tests)."""
    if concern in SALT_REGISTRY and SALT_REGISTRY[concern] != salt:
        raise ValueError(
            f"Concern '{concern}' already registered with salt "
            f"{SALT_REGISTRY[concern]:#x}, refusing to overwrite with {salt:#x}"
        )
    SALT_REGISTRY[concern] = salt


def make_rng(base_seed: int, concern: str = "master") -> np.random.Generator:
    """Return a stream-isolated ``numpy.random.Generator`` for ``concern``.

    ``base_seed`` is the user-facing seed (e.g. ``--seed 42``); ``concern``
    must already be registered in ``SALT_REGISTRY``. The returned RNG is
    independent of every other concern's RNG.
    """
    if concern not in SALT_REGISTRY:
        raise KeyError(
            f"Unknown RNG concern '{concern}'. Register it in "
            f"synth_datagen.rng.SALT_REGISTRY before use. Existing concerns: "
            f"{sorted(SALT_REGISTRY)}"
        )
    return np.random.default_rng(seed=int(base_seed) ^ SALT_REGISTRY[concern])
