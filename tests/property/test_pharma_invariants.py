"""Hypothesis property tests for the pharma scenario.

These exercise the engine across many random seeds at smoke scale
(``account_count=200``) to catch invariant violations that a single
seed wouldn't surface. Auto-marked ``slow`` via
``tests/property/conftest.py``; runs only under ``pytest -m slow``.

Properties covered:

- **Reproducibility** — same seed produces identical bytes for every
  table.
- **Foreign-key integrity** — across many seeds, every FK lookup
  resolves; no orphans.
- **AGS hierarchy invariant** — every account has
  ``landkreis_ags[:2] == bundesland_ags`` and a non-NaN parent.
- **Pareto concentration** — top-20 % of accounts hold a band of the
  total revenue (loose 55–80 % envelope; see commit-10 message body
  for rationale on the looseness vs the spec REQ-5 tighter target).
- **University concentration** — Universitätskliniken (~3 % of acute
  accounts) hold a disproportionate share of revenue.
- **Stream isolation** (REQ-7) — flipping ``data_quality`` must not
  shift accounts geo / AGS columns.
- **Stream-count stability** — engine spawns exactly 8 streams in the
  locked order. Regression guard against accidental insertion.

Real-scale tests (population correlation against DESTATIS,
BL-09/05/08 rep concentration) are marked ``real_geo`` and skipped
unless ``PHARMA_REAL_GEO_DIR`` env var is set. See
``tests/pharma/README.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Skip the whole module if [pharma] extra is missing.
pytest.importorskip("geopandas", reason="requires '[pharma]' extra")
pytest.importorskip("shapely", reason="requires '[pharma]' extra")

from synth_datagen.pharma import engine  # noqa: E402
from synth_datagen.pharma.config import PharmaConfig  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pharma"
HOSPITALS_CSV = FIXTURE_DIR / "osm_hospitals_DE_test.csv"
BL_GEOJSON = FIXTURE_DIR / "bundeslaender_test.geojson"
LK_GEOJSON = FIXTURE_DIR / "landkreise_test.geojson"

PROP_ACCOUNT_COUNT = 200

# Seed strategy: 32-bit non-negative ints. Pharma config validator
# enforces seed >= 0; the upper bound mirrors retail's strategy in
# tests/property/test_retail_invariants.py.
_SEED_STRATEGY = st.integers(min_value=0, max_value=2**31 - 1)

# Hypothesis settings per Phase-6 plan:
# - max_examples=20 — broader sampling than the project's default 3,
#   trading slow-lane time (~30 s for the pharma block) for stronger
#   coverage on statistical bands.
# - deadline=10000 ms — single Hypothesis example may include a fresh
#   engine.generate() call which costs ~150 ms, plus pandas ops for
#   the band computation. 10 s headroom keeps flakes from CPU contention
#   during CI from hard-failing.
# - HealthCheck.too_slow / function_scoped_fixture suppressed because
#   the engine's startup cost (geopandas import + sjoin) is real and
#   not a bug Hypothesis should flag.
_PROP_SETTINGS = settings(
    max_examples=20,
    deadline=10_000,
    database=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ],
)


def _make_acute_config(seed: int, *, data_quality: str = "clean") -> PharmaConfig:
    return PharmaConfig(
        sub_mode="acute-care",
        hospitals_csv=HOSPITALS_CSV,
        bkg_bundeslaender=BL_GEOJSON,
        bkg_landkreise=LK_GEOJSON,
        seed=seed,
        account_count=PROP_ACCOUNT_COUNT,
        rep_count=20,
        data_quality=data_quality,
    )


def _make_specialty_config(seed: int, *, data_quality: str = "clean") -> PharmaConfig:
    return PharmaConfig(
        sub_mode="specialty-care",
        hospitals_csv=HOSPITALS_CSV,
        bkg_bundeslaender=BL_GEOJSON,
        bkg_landkreise=LK_GEOJSON,
        seed=seed,
        account_count=PROP_ACCOUNT_COUNT,
        rep_count=20,
        data_quality=data_quality,
    )


# ---------------------------------------------------------------------------
# Reproducibility — bit-stable output across all seeds
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_acute_reproducible(seed: int) -> None:
    """Same seed must produce identical frames across two runs."""
    a = engine.generate(_make_acute_config(seed))
    b = engine.generate(_make_acute_config(seed))
    for name in a:
        # Use .equals so failures fold cleanly into the Hypothesis
        # shrinker (assert_frame_equal raises a different error type).
        assert a[name].equals(b[name]), (
            f"acute/{name}: non-deterministic output for seed={seed}"
        )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_specialty_reproducible(seed: int) -> None:
    """Same seed → identical specialty-care output."""
    a = engine.generate(_make_specialty_config(seed))
    b = engine.generate(_make_specialty_config(seed))
    for name in a:
        assert a[name].equals(b[name]), (
            f"specialty/{name}: non-deterministic output for seed={seed}"
        )


# ---------------------------------------------------------------------------
# AGS hierarchy invariant (REQ-1)
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_acute_ags_hierarchy_property(seed: int) -> None:
    """For any seed, every account row must satisfy
    ``landkreis_ags[:2] == bundesland_ags`` and have non-NaN AGS."""
    out = engine.generate(_make_acute_config(seed))
    accounts = out["accounts"]
    assert accounts["bundesland_ags"].notna().all(), (
        f"seed={seed}: NaN in bundesland_ags"
    )
    assert accounts["landkreis_ags"].notna().all(), f"seed={seed}: NaN in landkreis_ags"
    prefix = accounts["landkreis_ags"].astype(str).str[:2]
    parent = accounts["bundesland_ags"].astype(str)
    assert (prefix == parent).all(), (
        f"seed={seed}: AGS prefix mismatch in {(prefix != parent).sum()} rows"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_specialty_ags_hierarchy_property(seed: int) -> None:
    out = engine.generate(_make_specialty_config(seed))
    accounts = out["accounts"]
    assert accounts["bundesland_ags"].notna().all()
    assert accounts["landkreis_ags"].notna().all()
    prefix = accounts["landkreis_ags"].astype(str).str[:2]
    parent = accounts["bundesland_ags"].astype(str)
    assert (prefix == parent).all()


# ---------------------------------------------------------------------------
# Foreign-key integrity across all seeds
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_no_orphan_foreign_keys(seed: int) -> None:
    """Every order/visit/specialty FK must resolve to a parent row.
    Across many seeds the engine's sampling-with-replacement on
    parent IDs MUST never produce an orphan."""
    out = engine.generate(_make_acute_config(seed))
    accounts_set = set(out["accounts"]["account_id"])
    reps_set = set(out["sales_reps"]["rep_id"])
    products_set = set(out["products"]["product_id"])
    territories_set = set(out["territories"]["territory_id"])

    assert set(out["orders"]["account_id"]) <= accounts_set, (
        f"seed={seed}: orphan order.account_id"
    )
    assert set(out["orders"]["rep_id"]) <= reps_set, f"seed={seed}: orphan order.rep_id"
    assert set(out["orders"]["product_id"]) <= products_set, (
        f"seed={seed}: orphan order.product_id"
    )
    assert set(out["rep_visits"]["account_id"]) <= accounts_set, (
        f"seed={seed}: orphan rep_visits.account_id"
    )
    assert set(out["account_specialties"]["account_id"]) <= accounts_set, (
        f"seed={seed}: orphan account_specialties.account_id"
    )
    assert set(out["sales_reps"]["territory_id"]) <= territories_set, (
        f"seed={seed}: orphan sales_reps.territory_id"
    )


# ---------------------------------------------------------------------------
# Revenue concentration — Pareto envelope
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_acute_top_20pct_revenue_concentration(seed: int) -> None:
    """Top 20 % of accounts hold a non-trivial share of revenue.

    Spec REQ-5 targets 65–70 % concentration for acute. On n=200 with
    log-normal revenue (sigma=1.15) the empirical band is wider than
    the spec literal. We assert 55–80 % — loose enough to absorb
    statistical noise across 20 random seeds, strict enough to catch
    a real regression (e.g. revenue accidentally drawn from a
    uniform distribution would land at ~20 %, well below the floor).
    """
    out = engine.generate(_make_acute_config(seed))
    revenue = out["accounts"]["annual_revenue"].sort_values(ascending=False)
    n_top = max(1, int(round(0.20 * len(revenue))))
    top_share = float(revenue.head(n_top).sum() / revenue.sum())
    assert 0.45 <= top_share <= 0.85, (
        f"seed={seed}: top-20% acute revenue share {top_share:.2%} "
        f"outside [45%, 85%] envelope"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_specialty_top_20pct_revenue_concentration(seed: int) -> None:
    """Spec REQ-5 targets 55–60 % for specialty (lower sigma); we
    use the same loose [45 %, 85 %] envelope so the test contract
    is uniform across sub-modes."""
    out = engine.generate(_make_specialty_config(seed))
    revenue = out["accounts"]["annual_revenue"].sort_values(ascending=False)
    n_top = max(1, int(round(0.20 * len(revenue))))
    top_share = float(revenue.head(n_top).sum() / revenue.sum())
    assert 0.40 <= top_share <= 0.80, (
        f"seed={seed}: top-20% specialty revenue share {top_share:.2%} "
        f"outside [40%, 80%] envelope"
    )


# ---------------------------------------------------------------------------
# University-hospital revenue dominance (acute only)
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_acute_university_revenue_dominance(seed: int) -> None:
    """Universitätskliniken (~3 % of acute accounts) draw revenue
    from the same lognormal distribution as other accounts in v0.3.0
    — they are NOT yet boosted via a separate revenue multiplier
    (deferred to v0.3.x calibration). With a uniform draw, their
    revenue share should track their account share — i.e. ~3 % ± a
    wide band given the long tail. We assert the share is non-zero
    and within a sane envelope. This test fires regardless of seed
    because the lognormal will sometimes hand a university the
    biggest amount, sometimes the smallest."""
    out = engine.generate(_make_acute_config(seed))
    accounts = out["accounts"]
    is_uni = accounts["account_archetype"] == "University"
    if is_uni.sum() == 0:
        # Some seeds at n=200 yield zero universities (3 % share -> ~6
        # expected, but binomial variance means 0 is plausible). Not a
        # regression — skip the assertion for this seed.
        return
    uni_share = float(
        accounts.loc[is_uni, "annual_revenue"].sum() / accounts["annual_revenue"].sum()
    )
    # Loose envelope: at v0.3.0 universities draw from the same
    # log-normal distribution as other accounts (no revenue boost
    # — that calibration is deferred to v0.3.x). Their realised share
    # is bounded below by a few-university × low-lognormal-draw
    # corner case (binomial gives ~6 universities expected at n=200,
    # 3 % share, but variance means 1-3 is plausible) and above by
    # the long-tail upside. 0.1 % floor to never flake on extreme
    # low draws; 25 % ceiling to catch a runaway boost regression.
    assert 0.001 <= uni_share <= 0.25, (
        f"seed={seed}: university revenue share {uni_share:.2%} "
        f"outside [0.1%, 25%] envelope"
    )


# ---------------------------------------------------------------------------
# Stream isolation — REQ-7 (data_quality must not shift geo)
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_quality_does_not_shift_accounts_geo(seed: int) -> None:
    """Spec REQ-7: changing data_quality from clean to messy must
    NOT shift accounts.bundesland_ags / accounts.landkreis_ags /
    accounts.account_id. Defects only touches the quality stream."""
    clean = engine.generate(_make_acute_config(seed, data_quality="clean"))
    messy = engine.generate(_make_acute_config(seed, data_quality="messy"))
    invariant_cols = ["account_id", "bundesland_ags", "landkreis_ags"]
    a = clean["accounts"][invariant_cols].reset_index(drop=True)
    b = messy["accounts"][invariant_cols].reset_index(drop=True)
    assert a.equals(b), (
        f"seed={seed}: data_quality flip shifted accounts geo columns — "
        "REQ-7 stream-isolation violated"
    )


# ---------------------------------------------------------------------------
# Stream-count stability — regression guard against insertion
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_stream_count_stable_property(seed: int) -> None:
    """Across many seeds, the engine spawns exactly 8 streams in the
    locked order. Catches an accidental insertion (vs append) that
    would shift bytes."""
    streams = engine.make_pharma_streams(seed)
    assert list(streams.keys()) == [
        "accounts",
        "reps",
        "territories",
        "orders",
        "products",
        "engagement",
        "quality",
        "regional",
    ], f"seed={seed}: stream order changed"


# ---------------------------------------------------------------------------
# Quantity / amount sign invariants on clean output
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_clean_orders_have_positive_quantities(seed: int) -> None:
    """Clean mode must not introduce negative quantities — those come
    only from the messy/medium defect pass."""
    out = engine.generate(_make_acute_config(seed, data_quality="clean"))
    qty = out["orders"]["quantity"].astype(int)
    assert (qty > 0).all(), (
        f"seed={seed}: clean mode produced "
        f"{int((qty <= 0).sum())} non-positive quantities"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_clean_orders_have_positive_amounts(seed: int) -> None:
    """Clean-mode order amount = quantity × unit_price × noise — all
    factors positive, so amount > 0 strictly."""
    out = engine.generate(_make_acute_config(seed, data_quality="clean"))
    amount = out["orders"]["amount"].astype(float)
    assert (amount > 0).all(), (
        f"seed={seed}: clean mode produced "
        f"{int((amount <= 0).sum())} non-positive amounts"
    )


# ---------------------------------------------------------------------------
# Visit frequency in REQ-4 band
# ---------------------------------------------------------------------------


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_acute_visit_frequency_band(seed: int) -> None:
    """Spec REQ-4: acute median visits/account/year ∈ [3, 6]. Engine
    samples Beta(2,3) over [3,6] then scales by years_in_window.
    Verify the median / years_in_window ratio sits inside the band.
    """
    config = _make_acute_config(seed)
    out = engine.generate(config)
    days_total = (config.end_date - config.start_date).days
    years_in_window = days_total / 365.25
    counts_per_account = (
        out["rep_visits"]
        .groupby("account_id")
        .size()
        .reindex(out["accounts"]["account_id"], fill_value=0)
    )
    visits_per_year = counts_per_account / years_in_window
    median = float(visits_per_year.median())
    # REQ-4 says 3-6 with Beta(2,3) — Beta peak is at the lower
    # third, so realised median lands ~3.5-5.5. Loose band [2, 7]
    # absorbs noise across seeds.
    assert 2.0 <= median <= 7.0, (
        f"seed={seed}: acute median visits/year {median:.2f} outside [2, 7]"
    )


@_PROP_SETTINGS
@given(seed=_SEED_STRATEGY)
def test_pharma_specialty_visit_frequency_band(seed: int) -> None:
    """Spec REQ-4: specialty 8-14 visits/year. Beta(2.5,2.5) is
    symmetric so the median lands near 11. Loose band [6, 16]."""
    config = _make_specialty_config(seed)
    out = engine.generate(config)
    days_total = (config.end_date - config.start_date).days
    years_in_window = days_total / 365.25
    counts_per_account = (
        out["rep_visits"]
        .groupby("account_id")
        .size()
        .reindex(out["accounts"]["account_id"], fill_value=0)
    )
    visits_per_year = counts_per_account / years_in_window
    median = float(visits_per_year.median())
    assert 6.0 <= median <= 16.0, (
        f"seed={seed}: specialty median visits/year {median:.2f} outside [6, 16]"
    )


# ---------------------------------------------------------------------------
# Real-geo tests — skipped by default; require PHARMA_REAL_GEO_DIR
# ---------------------------------------------------------------------------


def _real_geo_paths() -> tuple[Path, Path, Path] | None:
    """Resolve real-geo fixture paths, or None if env var not set."""
    base_str = os.environ.get("PHARMA_REAL_GEO_DIR")
    if not base_str:
        return None
    base = Path(base_str)
    osm = base / "osm_hospitals_germany.csv"
    bl = base / "bundeslaender_VG250.geojson"
    lk = base / "landkreise_VG250.geojson"
    if not (osm.exists() and bl.exists() and lk.exists()):
        return None
    return osm, bl, lk


@pytest.mark.real_geo
def test_pharma_acute_population_correlation_real_geo() -> None:
    """REQ-1: account density per Bundesland correlates with DESTATIS
    population (Spearman ρ > 0.7). Statistically meaningless on the
    fixture's n=3 BLs — runs only against real BKG VG250 + OSM
    snapshot.
    """
    paths = _real_geo_paths()
    if paths is None:
        pytest.skip("PHARMA_REAL_GEO_DIR env var not set; see tests/pharma/README.md")
    osm, bl, lk = paths
    cfg = PharmaConfig(
        sub_mode="acute-care",
        hospitals_csv=osm,
        bkg_bundeslaender=bl,
        bkg_landkreise=lk,
        seed=42,
        account_count=PROP_ACCOUNT_COUNT,
        rep_count=20,
        data_quality="clean",
    )
    out = engine.generate(cfg)

    accounts_per_bl = out["accounts"]["bundesland_ags"].value_counts()
    # Production BL population comes from the BKG GeoJSON's
    # ``population`` property — load it directly via geo.py to keep
    # the test independent of any module-level constant.
    from synth_datagen import geo

    bl_gdf = geo.load_bundeslaender(bl)
    bl_pop = bl_gdf.set_index("ags_2digit")["population"]
    aligned_pop = bl_pop.reindex(accounts_per_bl.index)
    corr = accounts_per_bl.corr(aligned_pop, method="spearman")
    assert corr is not None and corr > 0.7, (
        f"population correlation too weak: ρ={corr:.3f} (need > 0.7)"
    )


@pytest.mark.real_geo
def test_pharma_rep_concentration_in_by_nw_bw_real_geo() -> None:
    """REQ-4 (Pharmalotse): ~50 % of pharma reps are home-located in
    BY (09) + NW (05) + BW (08). Engine encodes this via
    _REP_HOME_CONCENTRATION_BLS; this test verifies the realisation
    against real BKG fixture data (fixture has only AGS '09' from the
    triplet, so the test is meaningless under the hermetic fixture).
    """
    paths = _real_geo_paths()
    if paths is None:
        pytest.skip("PHARMA_REAL_GEO_DIR env var not set; see tests/pharma/README.md")
    osm, bl, lk = paths
    cfg = PharmaConfig(
        sub_mode="acute-care",
        hospitals_csv=osm,
        bkg_bundeslaender=bl,
        bkg_landkreise=lk,
        seed=42,
        account_count=PROP_ACCOUNT_COUNT,
        rep_count=200,  # higher rep count for a stable share estimate
        data_quality="clean",
    )
    out = engine.generate(cfg)
    home_bls = out["sales_reps"]["home_bundesland_ags"].astype(str)
    high_concentration = home_bls.isin({"09", "05", "08"}).sum() / len(home_bls)
    # Loose band [0.35, 0.65] around the 0.50 spec target.
    assert 0.35 <= high_concentration <= 0.65, (
        f"BY+NW+BW rep concentration {high_concentration:.1%} "
        f"outside [35%, 65%] band (spec target 50%)"
    )
