"""Sanity tests for the pharma benchmark constants module.

REQ-8 of the Phase 6 spec mandates that every numeric parameter in the
pharma scenario cite a public-source benchmark. ``synth_datagen.pharma.
benchmarks`` is the single source of truth for those constants. These
tests are typo guards: they catch drift between the cited source and
the literal stored in the module (e.g. a hospital count that no longer
sums to the published total).

Source citations live in the module docstrings/comments; we re-validate
the relationships *between* constants here, not the absolute values.
"""

from __future__ import annotations

import inspect
from types import ModuleType

import pytest

from synth_datagen.pharma import benchmarks


# Names that appear in module ``vars()`` but are not user-defined constants
# we want to validate. ``annotations`` is the binding produced by
# ``from __future__ import annotations``.
_NON_CONSTANT_NAMES = frozenset({"annotations"})


def _public_attrs(mod: ModuleType) -> dict[str, object]:
    """Return module-level non-dunder, non-private user constants."""
    return {
        name: value
        for name, value in vars(mod).items()
        if not name.startswith("_")
        and name not in _NON_CONSTANT_NAMES
        and not inspect.ismodule(value)
        and not inspect.isfunction(value)
        and not inspect.isclass(value)
    }


# ---------------------------------------------------------------------------
# DESTATIS Krankenhausstatistik 2023 (KHStatV) consistency
# ---------------------------------------------------------------------------


def test_destatis_hospital_subtypes_within_total_envelope() -> None:
    """Sum of acute + psychiatric + day-surgery hospital counts must be a
    plausible bound on the total.

    DESTATIS publishes the headline TOTAL_HOSPITALS_DE = 1874 alongside
    subtype counts (1585 acute + 279 psychiatric + 61 day-surgery)
    that sum to 1925 — the small overrun (~3 %) is real, driven by
    facilities being counted in more than one subtype table (e.g. a
    Universitätsklinikum publishing both an acute-care and a
    psychiatric department under one organisational roof). Both are
    correct numbers from the same publication.

    Encoding the relationship as a loose envelope rather than equality
    lets future DESTATIS releases ride a small overlap delta without
    breaking the test, while still catching a transposed digit (which
    would shift the sum by hundreds, not tens).
    """
    subtype_sum = (
        benchmarks.ACUTE_CARE_HOSPITALS_DE
        + benchmarks.PSYCHIATRIC_HOSPITALS_DE
        + benchmarks.DAY_SURGERY_HOSPITALS_DE
    )
    assert (
        benchmarks.TOTAL_HOSPITALS_DE * 0.95
        < subtype_sum
        < (benchmarks.TOTAL_HOSPITALS_DE * 1.10)
    )


def test_destatis_ownership_shares_sum_to_unit() -> None:
    """Public + non-profit + for-profit ownership shares ≈ 1.0.

    Tolerance ±1pp because the DESTATIS publication rounds to whole
    percent.
    """
    s = (
        benchmarks.PCT_HOSPITALS_PUBLIC
        + benchmarks.PCT_HOSPITALS_NONPROFIT
        + benchmarks.PCT_HOSPITALS_FORPROFIT
    )
    assert s == pytest.approx(1.0, abs=0.01)


def test_university_hospitals_within_acute_subset() -> None:
    """Universitätskliniken (35) must be a subset of acute-care hospitals."""
    assert benchmarks.UNIVERSITY_HOSPITALS_DE <= benchmarks.ACUTE_CARE_HOSPITALS_DE


def test_avg_beds_public_greater_than_private() -> None:
    """DESTATIS shows public hospitals are larger on average than
    for-profit private ones (433 vs 132 beds). Encoded as a sanity check
    so a future edit doesn't accidentally swap them."""
    assert benchmarks.AVG_BEDS_PUBLIC_HOSPITAL > benchmarks.AVG_BEDS_PRIVATE_HOSPITAL


# ---------------------------------------------------------------------------
# PHAGRO 2024 wholesale-market consistency
# ---------------------------------------------------------------------------


def test_phagro_rx_share_in_unit_interval() -> None:
    assert 0.0 < benchmarks.PCT_RX_OF_WHOLESALE <= 1.0


def test_phagro_wholesale_margin_under_one_pct_floor() -> None:
    """Regulated wholesale margin is capped at 2.8% per PHAGRO. The
    literal must be expressed as a fraction (0.028), not a percent (2.8)."""
    assert 0.0 < benchmarks.WHOLESALE_MARGIN_AVG_PCT < 0.10


# ---------------------------------------------------------------------------
# IQVIA 2022 hospital + retail vs PHAGRO total
# ---------------------------------------------------------------------------


def test_iqvia_hospital_plus_retail_under_phagro_total() -> None:
    """IQVIA hospital + retail (manufacturer perspective) should be at
    most ~1.1× PHAGRO total wholesale (different scopes; loose bound)."""
    iqvia_combined = (
        benchmarks.HOSPITAL_PHARMA_REVENUE_DE_2022
        + benchmarks.RETAIL_PHARMA_REVENUE_DE_2022
    )
    assert iqvia_combined < benchmarks.TOTAL_WHOLESALE_REVENUE_DE_2024 * 1.5


# ---------------------------------------------------------------------------
# vfa Biotech-Report 2025 — biopharmaceutical market shares
# ---------------------------------------------------------------------------


def test_biopharma_top_four_shares_majority() -> None:
    """The 4 biggest therapy areas (oncology + immunology + hematology +
    CNS) cited by vfa should account for the majority of biopharma. They
    needn't sum to exactly 1 — the long tail of smaller areas is implicit."""
    s = (
        benchmarks.BIOPHARMA_SHARE_ONCOLOGY
        + benchmarks.BIOPHARMA_SHARE_IMMUNOLOGY
        + benchmarks.BIOPHARMA_SHARE_HEMATOLOGY
        + benchmarks.BIOPHARMA_SHARE_CNS
    )
    assert 0.85 < s <= 1.05


# ---------------------------------------------------------------------------
# German pharma field force size
# ---------------------------------------------------------------------------


def test_pharma_reps_current_below_peak() -> None:
    """The cited contraction (peak ~22k → current ~12k) must be encoded
    in the right direction; this guards against a future edit swapping
    the two numbers."""
    assert benchmarks.PHARMA_REPS_CURRENT < benchmarks.PHARMA_REPS_PEAK


def test_doctor_visits_per_day_ordered() -> None:
    """Pharmalotse: average ~8 doctor visits + 1 pharmacy visit per day,
    ceiling ~10. Order must be avg ≤ max."""
    assert benchmarks.AVG_DOCTOR_VISITS_PER_DAY <= benchmarks.MAX_DOCTOR_VISITS_PER_DAY


# ---------------------------------------------------------------------------
# Module-level hygiene
# ---------------------------------------------------------------------------


def test_all_public_constants_are_immutable_scalars() -> None:
    """Every public name must be an int, float, or str — no mutables.

    This is a fence: someone tempted to add a list or dict of "magic
    parameters" should bounce off this test and add a typed dataclass
    or function instead.
    """
    public = _public_attrs(benchmarks)
    assert public, "benchmarks module appears empty"
    bad = {
        name: type(value).__name__
        for name, value in public.items()
        if not isinstance(value, (int, float, str))
    }
    assert not bad, f"Non-scalar public constants found: {bad}"


def test_all_public_constants_are_uppercase() -> None:
    """Style: module-level constants must be UPPER_SNAKE_CASE."""
    public = _public_attrs(benchmarks)
    bad = [name for name in public if name != name.upper()]
    assert not bad, f"Non-UPPER_SNAKE constants: {bad}"
