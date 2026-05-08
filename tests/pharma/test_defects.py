"""Tests for ``synth_datagen.pharma.defects``.

Defects mutate the engine's output tables in place to inject the 8
quality issues documented in the Phase 6 spec
(``prompts/pharma/05_implementation.md`` §"DATA QUALITY INJECTION"):

| # | Name                                  | Table     | Medium rate |
|---|---------------------------------------|-----------|-------------|
| 1 | hospital_name_variants                | accounts  |  0.4 %      |
| 2 | plz_format_inconsistency              | accounts  |  0.6 %      |
| 3 | bundesland_name_iso_mismatch          | accounts  |  0.3 %      |
| 4 | negative_order_quantities             | orders    |  1.1 %      |
| 5 | order_visit_date_misalignment         | orders    |  0.8 %      |
| 6 | account_rep_assignment_inconsistency  | orders    |  0.5 %      |
| 7 | duplicate_atc_old_new_pzn             | products  |  0.3 %      |
| 8 | coordinate_precision_inconsistency    | accounts  |  1.0 %      |

Locked invariants:
- ``clean`` mode: zero rows mutated, identical to input.
- ``messy`` mode: rates are 4× medium across all 8 defects.
- The defect pass uses ONLY the ``quality`` RNG stream — no draws
  from ``accounts``, ``orders``, ``reps``, ``products``,
  ``territories``, ``engagement``, or ``regional`` streams. This is
  the spec REQ-7 stream-isolation guarantee.
- Determinism: same seed + same input → same output bytes.

The defects module operates on a ``Tables`` mapping (dict[str,
DataFrame]) so it can run before the engine exists — these tests
build minimal synthetic input directly.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from synth_datagen.pharma import defects


# ---------------------------------------------------------------------------
# Synthetic input fixtures (kept tiny + deterministic for fast tests)
# ---------------------------------------------------------------------------


def _make_accounts(n: int = 1000) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "account_id": [f"a_{i:06d}" for i in range(n)],
            "name": [f"Klinikum Stadt-{i}" for i in range(n)],
            "plz": [f"{10000 + i:05d}" for i in range(n)],
            "bundesland": ["Bayern"] * n,
            "latitude": np.linspace(50.0, 53.0, n).round(6),
            "longitude": np.linspace(10.0, 14.0, n).round(6),
        }
    )


def _make_orders(n: int = 2000, n_reps: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "order_id": [f"o_{i:08d}" for i in range(n)],
            "account_id": [f"a_{i % 500:06d}" for i in range(n)],
            "rep_id": [f"r_{int(rng.integers(0, n_reps)):04d}" for _ in range(n)],
            "product_id": [f"p_{i % 30:04d}" for i in range(n)],
            "order_date": pd.to_datetime(
                [date(2024, 1, 1) + timedelta(days=i % 365) for i in range(n)]
            ),
            "quantity": np.full(n, 10, dtype=int),
            "amount": np.full(n, 250.0),
        }
    )


def _make_products(n: int = 30) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "product_id": [f"p_{i:04d}" for i in range(n)],
            "pzn": [f"{10000000 + i:08d}" for i in range(n)],
            "atc_code": [f"L01XC{(i % 10):02d}" for i in range(n)],
            "product_name": [f"Synthetic-Product-{i}" for i in range(n)],
        }
    )


def _make_tables(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Bundle the three tables defects mutate into a Tables-shaped dict."""
    return {
        "accounts": _make_accounts(),
        "orders": _make_orders(),
        "products": _make_products(),
    }


def _hash_tables(tables: dict[str, pd.DataFrame]) -> dict[str, str]:
    """SHA-256 of each table's CSV bytes — for byte-equality checks."""
    import hashlib

    return {
        name: hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()
        for name, df in tables.items()
    }


# ---------------------------------------------------------------------------
# Clean mode: zero defects
# ---------------------------------------------------------------------------


def test_clean_mode_does_not_mutate_any_table() -> None:
    tables_before = _make_tables()
    before_hashes = _hash_tables(tables_before)

    rng = np.random.default_rng(seed=42)
    after = defects.apply_pharma_defects(_make_tables(), level="clean", rng=rng)
    after_hashes = _hash_tables(after)

    for name, h in before_hashes.items():
        assert after_hashes[name] == h, (
            f"clean mode mutated table {name!r} (hash differs)"
        )


def test_clean_mode_consumes_no_rng_state() -> None:
    """Clean mode must not draw from the quality stream at all — there's
    nothing to randomise. A clean-mode pass that consumed RNG state
    would shift downstream draws if the caller reused the same RNG."""
    rng_a = np.random.default_rng(seed=42)
    rng_b = np.random.default_rng(seed=42)
    defects.apply_pharma_defects(_make_tables(), level="clean", rng=rng_a)
    # rng_b never touched; a draw from each must be equal.
    assert rng_a.integers(0, 1_000_000) == rng_b.integers(0, 1_000_000)


# ---------------------------------------------------------------------------
# Medium / messy: documented rates ± Hypothesis tolerance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level,multiplier",
    [
        ("medium", 1.0),
        ("messy", 4.0),
    ],
)
def test_negative_order_quantities_rate_within_tolerance(
    level: str, multiplier: float
) -> None:
    """Defect 4: 1.1 % of orders flipped to negative quantity at
    medium; 4× = 4.4 % at messy. Tolerance ±50 % of the expected
    count to absorb the random-draw noise on a 2000-row table."""
    tables = _make_tables()
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects(tables, level=level, rng=rng)

    n_total = len(out["orders"])
    n_negative = int((out["orders"]["quantity"] < 0).sum())
    expected_rate = 0.011 * multiplier
    expected_count = n_total * expected_rate
    # Loose absolute window so the test isn't flaky on small inputs.
    lo = max(1, int(round(expected_count * 0.5)))
    hi = max(2, int(round(expected_count * 1.5)) + 1)
    assert lo <= n_negative <= hi, (
        f"{level}: expected ~{expected_count:.1f} negative quantities "
        f"(±50 %), got {n_negative} out of {n_total}"
    )


@pytest.mark.parametrize(
    "level,base_rate,multiplier",
    [
        ("medium", 0.010, 1.0),  # coordinate_precision_inconsistency
        ("messy", 0.010, 4.0),
    ],
)
def test_coordinate_precision_inconsistency_rate(
    level: str, base_rate: float, multiplier: float
) -> None:
    """Defect 8: 1.0 % of accounts have lat/lon rounded to 3 decimals
    instead of 6 (medium); 4 % at messy."""
    tables = _make_tables()
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects(tables, level=level, rng=rng)

    n_total = len(out["accounts"])
    # Detect: a row whose latitude does NOT exactly equal its 6-decimal
    # version is the unaffected case; rounding to 3 decimals truncates
    # the trailing 3 decimals so the value matches its 3-decimal
    # rounded form.
    rounded3 = out["accounts"]["latitude"].round(3)
    is_3dp = (out["accounts"]["latitude"] - rounded3).abs() < 1e-9
    # The original input has lat values evenly spaced — most are NOT
    # equal to their 3-decimal version. Defects flip a subset to be
    # equal. Count those that are 3dp AND were not 3dp in the input.
    input_lat = _make_accounts()["latitude"]
    input_rounded3 = input_lat.round(3)
    input_is_3dp = (input_lat - input_rounded3).abs() < 1e-9
    flipped = int(((is_3dp) & (~input_is_3dp)).sum())
    expected = n_total * base_rate * multiplier
    lo = max(1, int(round(expected * 0.5)))
    hi = max(2, int(round(expected * 1.5)) + 1)
    assert lo <= flipped <= hi, (
        f"{level}: expected ~{expected:.1f} 3-dp lat rows, got {flipped}"
    )


# ---------------------------------------------------------------------------
# Stream-isolation invariant — the spec REQ-7 critical guard
# ---------------------------------------------------------------------------


def test_messy_input_tables_are_only_mutated_via_quality_rng_when_quality_rng_provided() -> (
    None
):
    """The defect pass must accept and use ONLY the rng argument
    passed to it. If the function pulled additional state from the
    table contents themselves (e.g. via pandas sample default RNG),
    two runs with the same external rng but different *internal*
    seeds would diverge. We exercise that by feeding two equivalent
    tables with the same external rng — output must be byte-identical.
    """
    tables_a = _make_tables()
    tables_b = _make_tables()
    rng_a = np.random.default_rng(seed=42)
    rng_b = np.random.default_rng(seed=42)
    out_a = defects.apply_pharma_defects(tables_a, level="medium", rng=rng_a)
    out_b = defects.apply_pharma_defects(tables_b, level="medium", rng=rng_b)
    assert _hash_tables(out_a) == _hash_tables(out_b)


def test_quality_rng_state_advances_in_medium_and_messy() -> None:
    """Sanity: a non-clean defect pass advances the RNG state.
    Subsequent draws from the same RNG instance must differ from
    untouched-RNG draws. Catches a bug where we accidentally
    short-circuit the function for a level that should be active."""
    untouched = np.random.default_rng(seed=42)
    untouched_first = int(untouched.integers(0, 1_000_000))

    rng = np.random.default_rng(seed=42)
    defects.apply_pharma_defects(_make_tables(), level="medium", rng=rng)
    after_medium = int(rng.integers(0, 1_000_000))

    assert after_medium != untouched_first, (
        "medium-mode defect pass did not advance the quality RNG state"
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_same_seed_same_output() -> None:
    rng_a = np.random.default_rng(seed=42)
    rng_b = np.random.default_rng(seed=42)
    out_a = defects.apply_pharma_defects(_make_tables(), level="medium", rng=rng_a)
    out_b = defects.apply_pharma_defects(_make_tables(), level="medium", rng=rng_b)
    assert _hash_tables(out_a) == _hash_tables(out_b)


def test_different_seeds_produce_different_outputs() -> None:
    rng_a = np.random.default_rng(seed=42)
    rng_b = np.random.default_rng(seed=43)
    out_a = defects.apply_pharma_defects(_make_tables(), level="medium", rng=rng_a)
    out_b = defects.apply_pharma_defects(_make_tables(), level="medium", rng=rng_b)
    assert _hash_tables(out_a) != _hash_tables(out_b)


# ---------------------------------------------------------------------------
# Per-defect smoke: each documented defect produces SOME mutation at
# medium (positive rate * 1000-row tables → at least one row affected
# with very high probability).
# ---------------------------------------------------------------------------


def test_hospital_name_variants_at_medium_produces_changes() -> None:
    """Defect 1: ~0.4 % of accounts get a name variant. On 1000 rows,
    expected count is ~4; probability of zero changes is < 2 %."""
    tables = _make_tables()
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects(tables, level="medium", rng=rng)
    before = _make_accounts()["name"].tolist()
    after = out["accounts"]["name"].tolist()
    assert before != after, "no hospital name variants applied at medium"


def test_bundesland_iso_mismatch_at_medium_produces_changes() -> None:
    """Defect 3: 0.3 % of accounts have a Bundesland format swap.
    Detect: any row whose bundesland is no longer 'Bayern'."""
    tables = _make_tables()
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects(tables, level="medium", rng=rng)
    swapped = (out["accounts"]["bundesland"] != "Bayern").sum()
    assert swapped > 0


def test_plz_format_inconsistency_at_medium_produces_changes() -> None:
    """Defect 2: 0.6 % of accounts get a PLZ format mutation."""
    tables = _make_tables()
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects(tables, level="medium", rng=rng)
    before = _make_accounts()["plz"].astype(str).tolist()
    after = out["accounts"]["plz"].astype(str).tolist()
    assert before != after


def test_duplicate_atc_old_new_pzn_at_medium_adds_rows() -> None:
    """Defect 7: 0.3 % of products get a duplicate-row entry with a
    new PZN. The output products table grows by exactly that count."""
    tables = _make_tables()
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects(tables, level="medium", rng=rng)
    # 0.3 % of 30 = 0.09 → rounds to at least 1 dup at medium.
    assert len(out["products"]) >= len(_make_products()) + 1


# ---------------------------------------------------------------------------
# Bad-input guards
# ---------------------------------------------------------------------------


def test_rejects_unknown_level() -> None:
    rng = np.random.default_rng(seed=42)
    with pytest.raises(ValueError, match="level|clean|medium|messy"):
        defects.apply_pharma_defects(_make_tables(), level="extra-spicy", rng=rng)


def test_returns_a_mapping_with_same_table_names() -> None:
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects(_make_tables(), level="medium", rng=rng)
    assert set(out.keys()) == {"accounts", "orders", "products"}


# ---------------------------------------------------------------------------
# Defensive early-exit branches: malformed input must be a no-op, not
# a crash. These cover the (df is None / empty / missing-column) and
# (n == 0) paths in each per-defect function.
# ---------------------------------------------------------------------------


def test_empty_tables_dict_returns_empty_dict() -> None:
    """No tables at all → no defects fired, nothing to return."""
    rng = np.random.default_rng(seed=42)
    out = defects.apply_pharma_defects({}, level="medium", rng=rng)
    assert out == {}


def test_empty_dataframes_do_not_crash() -> None:
    """Each table present but with zero rows. Defect functions must
    short-circuit on len==0 rather than try to .sample() from an
    empty frame."""
    rng = np.random.default_rng(seed=42)
    empty_tables = {
        "accounts": pd.DataFrame(
            columns=[
                "account_id",
                "name",
                "plz",
                "bundesland",
                "latitude",
                "longitude",
            ]
        ),
        "orders": pd.DataFrame(
            columns=[
                "order_id",
                "account_id",
                "rep_id",
                "product_id",
                "order_date",
                "quantity",
            ]
        ),
        "products": pd.DataFrame(columns=["product_id", "pzn", "atc_code"]),
    }
    out = defects.apply_pharma_defects(empty_tables, level="messy", rng=rng)
    assert all(df.empty for df in out.values())


def test_missing_columns_do_not_crash() -> None:
    """A table present but lacking the column a defect targets — the
    defect must skip that mutation, not raise KeyError. Defends
    against the engine evolving to drop a column the defect module
    expected (a v0.3.x API hazard)."""
    rng = np.random.default_rng(seed=42)
    minimal = {
        "accounts": pd.DataFrame(
            {"account_id": ["a_000"]}
        ),  # missing name/plz/bundesland/lat/lon
        "orders": pd.DataFrame(
            {"order_id": ["o_000"]}
        ),  # missing quantity/order_date/rep_id
        "products": pd.DataFrame({"product_id": ["p_000"]}),  # missing pzn
    }
    # Must not raise.
    out = defects.apply_pharma_defects(minimal, level="messy", rng=rng)
    assert set(out.keys()) == {"accounts", "orders", "products"}


def test_single_rep_table_skips_rep_assignment_inconsistency() -> None:
    """Defect 6 needs at least two distinct rep_ids to swap between.
    With only one rep in the orders table, the swap is a no-op
    (impossible to introduce inconsistency with no alternative rep)."""
    rng = np.random.default_rng(seed=42)
    tables = _make_tables()
    tables["orders"]["rep_id"] = "r_solo"  # collapse to one unique rep
    before_reps = set(tables["orders"]["rep_id"])
    out = defects.apply_pharma_defects(tables, level="messy", rng=rng)
    after_reps = set(out["orders"]["rep_id"])
    assert after_reps == before_reps, "single-rep input had reps mutated"


def test_bundesland_aliases_only_swap_canonical_names() -> None:
    """Defect 3 only swaps when the row's existing bundesland matches
    a canonical entry in _BUNDESLAND_ALIASES. Already-aliased rows
    pass through unchanged. Verifies the .get(canonical) is None
    short-circuit."""
    rng = np.random.default_rng(seed=42)
    tables = _make_tables()
    # Pre-set every account to an alias ('BY') — defect 3 must not
    # swap further (it doesn't know how to round-trip 'BY' →
    # 'Bayern').
    tables["accounts"]["bundesland"] = "BY"
    out = defects.apply_pharma_defects(tables, level="messy", rng=rng)
    assert (out["accounts"]["bundesland"] == "BY").all()
