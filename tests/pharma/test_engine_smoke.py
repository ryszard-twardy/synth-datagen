"""Smoke tests for ``synth_datagen.pharma.engine.generate``.

Engine smoke = "did the 8-table generation actually produce 8
DataFrames with the right columns and FK consistency, on a tiny
account_count, against the hermetic fixtures, in well under a
second?".

Property-based realism tests (Pareto coefficient, population
correlation, revenue concentration bands) live in commit 10's
``tests/property/test_pharma_invariants.py``. This file is the
gate that says "engine.generate runs end-to-end, returns a dict,
and the schema is what the spec promised."

Tests are skipped when the ``[pharma]`` extra is missing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Skip the whole module if geopandas isn't available.
pytest.importorskip("geopandas", reason="requires '[pharma]' extra")
pytest.importorskip("shapely", reason="requires '[pharma]' extra")

from synth_datagen.pharma import engine  # noqa: E402
from synth_datagen.pharma.config import PharmaConfig  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pharma"
HOSPITALS_CSV = FIXTURE_DIR / "osm_hospitals_DE_test.csv"
BL_GEOJSON = FIXTURE_DIR / "bundeslaender_test.geojson"
LK_GEOJSON = FIXTURE_DIR / "landkreise_test.geojson"

# Smoke-test scale per the Phase 6 plan: 200 accounts. Big enough for
# Pareto / concentration patterns to surface; small enough to keep
# every smoke test under ~2 s.
SMOKE_ACCOUNT_COUNT = 200

EXPECTED_TABLE_NAMES: tuple[str, ...] = (
    "accounts",
    "sales_reps",
    "territories",
    "products",
    "orders",
    "rep_visits",
    "account_specialties",
    "geographic_metadata",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _smoke_config(
    sub_mode: str = "acute-care",
    *,
    seed: int = 42,
    data_quality: str = "clean",
    account_count: int = SMOKE_ACCOUNT_COUNT,
) -> PharmaConfig:
    """Convenience: build a PharmaConfig wired to the hermetic fixture."""
    return PharmaConfig(
        sub_mode=sub_mode,
        hospitals_csv=HOSPITALS_CSV,
        bkg_bundeslaender=BL_GEOJSON,
        bkg_landkreise=LK_GEOJSON,
        seed=seed,
        account_count=account_count,
        rep_count=20,
        data_quality=data_quality,
    )


# ---------------------------------------------------------------------------
# Schema: 8 tables, expected column sets
# ---------------------------------------------------------------------------


def test_generate_returns_dict_of_dataframes() -> None:
    out = engine.generate(_smoke_config())
    assert isinstance(out, dict)
    for name in EXPECTED_TABLE_NAMES:
        assert name in out, f"missing table {name!r}"
        assert isinstance(out[name], pd.DataFrame), f"table {name!r} is not a DataFrame"


def test_generate_returns_exactly_eight_tables() -> None:
    out = engine.generate(_smoke_config())
    assert set(out.keys()) == set(EXPECTED_TABLE_NAMES)


def test_accounts_table_required_columns() -> None:
    out = engine.generate(_smoke_config())
    accounts = out["accounts"]
    expected = {
        "account_id",
        "name",
        "account_type",
        "account_archetype",
        "sub_mode",
        "bundesland_ags",
        "landkreis_ags",
        "latitude",
        "longitude",
        "ownership_type",
        "annual_revenue",
        "status",
    }
    missing = expected - set(accounts.columns)
    assert not missing, f"accounts missing columns: {missing}"


def test_orders_table_required_columns() -> None:
    out = engine.generate(_smoke_config())
    orders = out["orders"]
    expected = {
        "order_id",
        "account_id",
        "rep_id",
        "product_id",
        "order_date",
        "quantity",
        "amount",
    }
    missing = expected - set(orders.columns)
    assert not missing, f"orders missing columns: {missing}"


def test_geographic_metadata_is_single_row() -> None:
    out = engine.generate(_smoke_config())
    meta = out["geographic_metadata"]
    assert len(meta) == 1


# ---------------------------------------------------------------------------
# AGS hierarchy (engine wiring through geo.py)
# ---------------------------------------------------------------------------


def test_accounts_ags_hierarchy_invariant() -> None:
    """Spec REQ-1: every account has valid bundesland_ags + landkreis_ags
    with ``landkreis_ags[:2] == bundesland_ags``."""
    out = engine.generate(_smoke_config())
    accounts = out["accounts"]
    assert accounts["bundesland_ags"].notna().all()
    assert accounts["landkreis_ags"].notna().all()
    prefix_match = accounts["landkreis_ags"].astype(str).str[:2] == accounts[
        "bundesland_ags"
    ].astype(str)
    assert prefix_match.all(), (
        f"AGS hierarchy violation in {(~prefix_match).sum()} rows"
    )


def test_accounts_landkreis_ags_in_fixture_set() -> None:
    out = engine.generate(_smoke_config())
    fixture_lk_ags = {
        "01001",
        "01002",
        "01003",
        "01004",
        "09001",
        "09002",
        "09003",
        "09004",
        "11001",
        "11002",
        "11003",
        "11004",
    }
    actual = set(out["accounts"]["landkreis_ags"].astype(str))
    assert actual <= fixture_lk_ags, (
        f"unknown landkreis AGS in output: {actual - fixture_lk_ags}"
    )


# ---------------------------------------------------------------------------
# Cross-FK integrity
# ---------------------------------------------------------------------------


def test_orders_account_id_subset_of_accounts() -> None:
    out = engine.generate(_smoke_config())
    accounts_set = set(out["accounts"]["account_id"])
    orders_accounts = set(out["orders"]["account_id"])
    assert orders_accounts <= accounts_set, (
        f"orphan order.account_id values: {orders_accounts - accounts_set}"
    )


def test_orders_rep_id_subset_of_sales_reps() -> None:
    out = engine.generate(_smoke_config())
    rep_set = set(out["sales_reps"]["rep_id"])
    orders_reps = set(out["orders"]["rep_id"])
    assert orders_reps <= rep_set


def test_orders_product_id_subset_of_products() -> None:
    out = engine.generate(_smoke_config())
    prod_set = set(out["products"]["product_id"])
    orders_prods = set(out["orders"]["product_id"])
    assert orders_prods <= prod_set


def test_rep_visits_account_id_subset_of_accounts() -> None:
    out = engine.generate(_smoke_config())
    accounts_set = set(out["accounts"]["account_id"])
    visit_accounts = set(out["rep_visits"]["account_id"])
    assert visit_accounts <= accounts_set


def test_account_specialties_account_id_subset_of_accounts() -> None:
    out = engine.generate(_smoke_config())
    accounts_set = set(out["accounts"]["account_id"])
    spec_accounts = set(out["account_specialties"]["account_id"])
    assert spec_accounts <= accounts_set


def test_sales_reps_territory_id_subset_of_territories() -> None:
    out = engine.generate(_smoke_config())
    terr_set = set(out["territories"]["territory_id"])
    rep_terr = set(out["sales_reps"]["territory_id"])
    assert rep_terr <= terr_set


# ---------------------------------------------------------------------------
# Sub-mode shape
# ---------------------------------------------------------------------------


def test_acute_sub_mode_marker_on_every_account() -> None:
    out = engine.generate(_smoke_config(sub_mode="acute-care"))
    assert (out["accounts"]["sub_mode"] == "acute-care").all()


def test_specialty_sub_mode_marker_on_every_account() -> None:
    out = engine.generate(_smoke_config(sub_mode="specialty-care"))
    assert (out["accounts"]["sub_mode"] == "specialty-care").all()


def test_acute_archetypes_within_acute_subset() -> None:
    """Spec REQ-2: acute-care accounts use Krankenhaus tier labels
    only — University / Maximalversorger / Schwerpunktversorger /
    Grundversorger. No Specialist / MVZ leakage."""
    from synth_datagen.pharma.vocab import ACUTE_CARE_ARCHETYPES

    out = engine.generate(_smoke_config(sub_mode="acute-care"))
    archetypes = set(out["accounts"]["account_archetype"])
    leaked = archetypes - set(ACUTE_CARE_ARCHETYPES)
    assert not leaked, f"acute-care saw non-acute archetypes: {leaked}"


def test_specialty_archetypes_within_specialty_subset() -> None:
    from synth_datagen.pharma.vocab import SPECIALTY_CARE_ARCHETYPES

    out = engine.generate(_smoke_config(sub_mode="specialty-care"))
    archetypes = set(out["accounts"]["account_archetype"])
    leaked = archetypes - set(SPECIALTY_CARE_ARCHETYPES)
    assert not leaked, f"specialty-care saw non-specialty archetypes: {leaked}"


# ---------------------------------------------------------------------------
# Reproducibility — same seed → byte-identical output
# ---------------------------------------------------------------------------


def test_reproducibility_same_seed_same_output() -> None:
    out_a = engine.generate(_smoke_config(seed=42))
    out_b = engine.generate(_smoke_config(seed=42))
    for name in EXPECTED_TABLE_NAMES:
        assert out_a[name].equals(out_b[name]), f"non-deterministic table: {name!r}"


def test_different_seeds_produce_different_accounts() -> None:
    out_a = engine.generate(_smoke_config(seed=42))
    out_b = engine.generate(_smoke_config(seed=43))
    assert not out_a["accounts"].equals(out_b["accounts"])


# ---------------------------------------------------------------------------
# Stream isolation: data_quality must NOT shift accounts/orders/etc
# (Spec REQ-7. Pinned harder in commit-10 property tests; smoke
# pins the most important columns.)
# ---------------------------------------------------------------------------


def test_data_quality_clean_vs_messy_preserves_accounts_geo() -> None:
    """Per spec REQ-7, flipping data_quality must not shift account
    locations or AGS columns — those are produced upstream of the
    defects pass and use a different RNG stream."""
    clean = engine.generate(_smoke_config(seed=42, data_quality="clean"))
    messy = engine.generate(_smoke_config(seed=42, data_quality="messy"))

    invariant = ["account_id", "bundesland_ags", "landkreis_ags"]
    cleaned = clean["accounts"][invariant].reset_index(drop=True)
    messied = messy["accounts"][invariant].reset_index(drop=True)
    assert cleaned.equals(messied), (
        "data_quality flip shifted accounts geo columns — "
        "REQ-7 stream-isolation violated"
    )


# ---------------------------------------------------------------------------
# RNG architecture: 8 streams in locked order
# ---------------------------------------------------------------------------


def test_make_pharma_streams_returns_eight_named_streams() -> None:
    streams = engine.make_pharma_streams(base_seed=42)
    expected = [
        "accounts",
        "reps",
        "territories",
        "orders",
        "products",
        "engagement",
        "quality",
        "regional",
    ]
    assert list(streams.keys()) == expected, (
        "Stream count or order changed — would shift bytes for the "
        "same seed across all prior pharma seeds. If the change is "
        "intentional, document the version bump and update this test."
    )


def test_make_pharma_streams_each_is_a_generator() -> None:
    streams = engine.make_pharma_streams(base_seed=42)
    for name, rng in streams.items():
        assert isinstance(rng, np.random.Generator), (
            f"stream {name!r} is not a Generator"
        )


def test_make_pharma_streams_independent() -> None:
    """Each stream's first draw must differ from every other's."""
    streams = engine.make_pharma_streams(base_seed=42)
    first_draws = {
        name: int(rng.integers(0, 1_000_000)) for name, rng in streams.items()
    }
    assert len(set(first_draws.values())) == len(first_draws), (
        f"stream first-draws collide: {first_draws}"
    )


# ---------------------------------------------------------------------------
# No direct np.random.default_rng calls inside pharma/* (memory:
# saas_v3-spawn-slot-followup pattern). Pharma must derive every RNG
# from make_rng(seed, "pharma") via the central factory.
# ---------------------------------------------------------------------------


def test_no_direct_default_rng_calls_in_pharma_package() -> None:
    """Walk every .py under src/synth_datagen/pharma/ via AST and
    flag any ``np.random.default_rng(...)`` or
    ``numpy.random.default_rng(...)`` calls. Pharma must derive RNGs
    only from ``synth_datagen.rng.make_rng`` (the central factory).
    Direct calls would silently shift bytes and bypass the salt
    registry's collision check."""
    import ast

    pkg_root = Path(engine.__file__).resolve().parent
    py_files = list(pkg_root.rglob("*.py"))
    assert py_files, "no python files found under pharma/"

    offenders: list[tuple[Path, int]] = []
    for path in py_files:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            # Looking for: <something>.default_rng
            if node.attr != "default_rng":
                continue
            # Walk the chain: <root>.<...>.default_rng. If the root
            # is np or numpy, it's a violation.
            cursor = node.value
            while isinstance(cursor, ast.Attribute):
                cursor = cursor.value
            if isinstance(cursor, ast.Name) and cursor.id in {"np", "numpy"}:
                offenders.append((path.relative_to(pkg_root), node.lineno))

    assert not offenders, (
        f"direct np.random.default_rng calls in pharma/ "
        f"(use make_rng(seed, 'pharma').spawn(N) instead): {offenders}"
    )
