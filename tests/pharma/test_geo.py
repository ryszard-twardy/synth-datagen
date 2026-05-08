"""Tests for ``synth_datagen.geo`` — shared German-administrative-geometry
helpers used by the pharma scenario.

The module is shared (lives at ``src/synth_datagen/geo.py``, not under
``pharma/``) because the AGS hierarchy + spatial-join helpers are
reusable for any future scenario that touches German geography
(logistics warehouse routing, retail catchment analysis, etc.). It
depends on ``geopandas`` + ``shapely``, which are *only* installed via
the ``[pharma]`` optional extra. Tests in this file are skipped if the
extra is missing.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

# Whole-module skip if geopandas isn't available — `[pharma]` extra not
# installed. The skip is silent rather than xfailing because pharma is
# explicitly an opt-in scenario and other developers shouldn't be
# pestered.
gpd = pytest.importorskip("geopandas", reason="requires '[pharma]' extra")
pytest.importorskip("shapely", reason="requires '[pharma]' extra")

from synth_datagen import geo  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pharma"
BL_PATH = FIXTURE_DIR / "bundeslaender_test.geojson"
LK_PATH = FIXTURE_DIR / "landkreise_test.geojson"
HOSPITAL_PATH = FIXTURE_DIR / "osm_hospitals_DE_test.csv"


# ---------------------------------------------------------------------------
# Bundesländer / Landkreise loading
# ---------------------------------------------------------------------------


def test_load_bundeslaender_returns_geodataframe() -> None:
    bl = geo.load_bundeslaender(BL_PATH)
    assert isinstance(bl, gpd.GeoDataFrame)


def test_load_bundeslaender_three_features() -> None:
    bl = geo.load_bundeslaender(BL_PATH)
    assert len(bl) == 3


def test_load_bundeslaender_has_required_columns() -> None:
    bl = geo.load_bundeslaender(BL_PATH)
    for col in ("ags_2digit", "name", "population", "geometry"):
        assert col in bl.columns, f"missing column {col!r}"


def test_load_bundeslaender_crs_is_4326() -> None:
    """Production code reprojects BKG VG250 (EPSG:25832) to 4326 on
    load. The fixtures are authored in 4326 so the loader passes them
    through; either way, the returned CRS must be 4326."""
    bl = geo.load_bundeslaender(BL_PATH)
    assert bl.crs is not None
    assert bl.crs.to_epsg() == 4326


def test_loaders_reproject_25832_to_4326(tmp_path: Path) -> None:
    """Real BKG VG250 GeoJSONs ship in EPSG:25832 (UTM 32N). Both
    loaders must transparently reproject to 4326 so spatial joins
    against OSM (also 4326) are byte-consistent across releases. The
    fixtures themselves are 4326, so we round-trip through 25832 here
    to exercise the production code path.
    """
    # Reproject the fixture to 25832, write to disk, reload via the
    # loader, and confirm the round-trip lands back in 4326 with
    # geometry that maps back to roughly the original coords.
    src_bl = geo.load_bundeslaender(BL_PATH).to_crs(epsg=25832)
    bl_path_25832 = tmp_path / "bl_25832.geojson"
    src_bl.to_file(bl_path_25832, driver="GeoJSON")
    bl_back = geo.load_bundeslaender(bl_path_25832)
    assert bl_back.crs.to_epsg() == 4326
    # Round-trip preserves bounding-box of bundesländer to within 0.001°.
    src_bounds = geo.load_bundeslaender(BL_PATH).total_bounds
    back_bounds = bl_back.total_bounds
    for s, b in zip(src_bounds, back_bounds):
        assert abs(s - b) < 1e-3

    # Same drill for landkreise.
    src_lk = geo.load_landkreise(LK_PATH).to_crs(epsg=25832)
    lk_path_25832 = tmp_path / "lk_25832.geojson"
    src_lk.to_file(lk_path_25832, driver="GeoJSON")
    lk_back = geo.load_landkreise(lk_path_25832)
    assert lk_back.crs.to_epsg() == 4326


def test_load_landkreise_returns_geodataframe() -> None:
    lk = geo.load_landkreise(LK_PATH)
    assert isinstance(lk, gpd.GeoDataFrame)
    assert len(lk) == 12


def test_load_landkreise_has_parent_ags_column() -> None:
    lk = geo.load_landkreise(LK_PATH)
    assert "ags_5digit" in lk.columns
    assert "ags_2digit_parent" in lk.columns


# ---------------------------------------------------------------------------
# AGS hierarchy validation
# ---------------------------------------------------------------------------


def test_validate_ags_hierarchy_passes_on_fixture() -> None:
    bl = geo.load_bundeslaender(BL_PATH)
    lk = geo.load_landkreise(LK_PATH)
    # Must not raise.
    geo.validate_ags_hierarchy(lk, bl)


def test_validate_ags_hierarchy_raises_on_orphan_landkreis() -> None:
    """A Landkreis whose parent AGS doesn't appear in the BL set must
    fail loudly — this catches typos in BKG releases or stale
    snapshots."""
    bl = geo.load_bundeslaender(BL_PATH)
    lk = geo.load_landkreise(LK_PATH).copy()
    # Repoint one LK to a non-existent BL. Keep ags_5digit consistent
    # with the orphan parent so this test isolates the orphan check
    # rather than the prefix check.
    lk.loc[0, "ags_2digit_parent"] = "99"
    lk.loc[0, "ags_5digit"] = "99001"
    with pytest.raises(ValueError, match="orphan|parent|hierarchy"):
        geo.validate_ags_hierarchy(lk, bl)


def test_validate_ags_hierarchy_raises_on_prefix_mismatch() -> None:
    """A Landkreis whose ``ags_5digit[:2]`` doesn't match its
    ``ags_2digit_parent`` is internally inconsistent — also a typo
    surface."""
    bl = geo.load_bundeslaender(BL_PATH)
    lk = geo.load_landkreise(LK_PATH).copy()
    # Keep parent valid ('01' from fixture) but break the prefix.
    lk.loc[0, "ags_5digit"] = "98001"
    with pytest.raises(ValueError, match="prefix|hierarchy|mismatch"):
        geo.validate_ags_hierarchy(lk, bl)


# ---------------------------------------------------------------------------
# OSM hospital loading
# ---------------------------------------------------------------------------


def test_load_osm_hospitals_returns_dataframe() -> None:
    df = geo.load_osm_hospitals(HOSPITAL_PATH)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 20


def test_load_osm_hospitals_required_columns() -> None:
    df = geo.load_osm_hospitals(HOSPITAL_PATH)
    for col in ("osm_id", "latitude", "longitude", "amenity"):
        assert col in df.columns


# ---------------------------------------------------------------------------
# Spatial join
# ---------------------------------------------------------------------------


def test_spatial_join_assigns_correct_landkreis_known_point() -> None:
    """A hand-placed point at the centre of fixture LK ``01001`` must
    receive that LK's AGS, not any other."""
    lk = geo.load_landkreise(LK_PATH)
    # LK 01001 spans lat 52.5–53, lon 10–11. Centre = (52.75, 10.5).
    points = pd.DataFrame({"latitude": [52.75], "longitude": [10.5]})
    ags = geo.spatial_join_to_landkreis(points, lk)
    assert isinstance(ags, pd.Series)
    assert len(ags) == 1
    assert ags.iloc[0] == "01001"


def test_spatial_join_assigns_each_fixture_hospital_correctly() -> None:
    """All 20 fixture hospital rows fall inside one of the 12 fixture
    LKs. Spatial join must assign every row a valid AGS, no NaNs, and
    each AGS must exist in the LK fixture."""
    lk = geo.load_landkreise(LK_PATH)
    hospitals = geo.load_osm_hospitals(HOSPITAL_PATH)
    ags = geo.spatial_join_to_landkreis(hospitals, lk)
    assert ags.isna().sum() == 0
    valid_ags = set(lk["ags_5digit"])
    assert set(ags) <= valid_ags


def test_spatial_join_returns_nan_for_point_outside_polygons() -> None:
    """Points far from any fixture polygon must return NaN, not raise.
    Engine code can then decide whether to drop or impute."""
    lk = geo.load_landkreise(LK_PATH)
    # Atlantic Ocean — far from any LK.
    points = pd.DataFrame({"latitude": [0.0], "longitude": [0.0]})
    ags = geo.spatial_join_to_landkreis(points, lk)
    assert ags.isna().all()


def test_spatial_join_preserves_input_order() -> None:
    """The returned Series must align positionally with the input
    points so engine code can assign back via
    ``points["landkreis_ags"] = ags``."""
    lk = geo.load_landkreise(LK_PATH)
    points = pd.DataFrame(
        {
            "latitude": [52.75, 51.5, 50.75],
            "longitude": [10.5, 11.5, 13.5],
        }
    )
    ags = geo.spatial_join_to_landkreis(points, lk)
    assert len(ags) == len(points)
    # Reversing input order reverses the output.
    points_rev = points.iloc[::-1].reset_index(drop=True)
    ags_rev = geo.spatial_join_to_landkreis(points_rev, lk)
    assert list(ags) == list(ags_rev[::-1])


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------


def test_haversine_zero_distance_is_zero() -> None:
    d = geo.haversine_km(52.5, 13.4, 52.5, 13.4)
    assert d == pytest.approx(0.0, abs=1e-9)


def test_haversine_munich_to_berlin_roughly_504km() -> None:
    """Munich (~48.137, 11.575) → Berlin (~52.520, 13.405) is ~504 km
    great-circle. Allow ±5 km tolerance."""
    d = geo.haversine_km(48.137, 11.575, 52.520, 13.405)
    assert 499 < d < 509


def test_haversine_symmetric() -> None:
    d_ab = geo.haversine_km(48.137, 11.575, 52.520, 13.405)
    d_ba = geo.haversine_km(52.520, 13.405, 48.137, 11.575)
    assert d_ab == pytest.approx(d_ba, abs=1e-9)


def test_haversine_one_degree_at_equator_is_about_111km() -> None:
    """1° of longitude at the equator is ~111.195 km — the canonical
    sanity check for any haversine implementation."""
    d = geo.haversine_km(0.0, 0.0, 0.0, 1.0)
    assert 110 < d < 112


def test_haversine_returns_plain_float() -> None:
    """Lightweight: not a numpy scalar. Engine code passes the result
    into pandas operations that prefer plain floats."""
    d = geo.haversine_km(0.0, 0.0, 0.0, 1.0)
    assert isinstance(d, float)
    assert math.isfinite(d)


# ---------------------------------------------------------------------------
# Internal hygiene — geopandas import must be lazy
# ---------------------------------------------------------------------------


def test_geo_module_top_level_does_not_import_geopandas_eagerly() -> None:
    """Importing ``synth_datagen.geo`` must not unconditionally import
    geopandas at module top — that would defeat the optional-extra
    packaging (``import synth_datagen.geo`` would crash for users
    without the extra).

    The module should import geopandas/shapely only inside functions
    that need them, or guarded by ``if TYPE_CHECKING:``. This test
    inspects the source for top-level imports.
    """
    src_path = Path(geo.__file__)
    text = src_path.read_text(encoding="utf-8")

    # Pre-def block: everything before the first ``def``. Top-level
    # imports live here.
    pre_def = text.split("\ndef ", 1)[0]

    # Walk lines, tracking ``if TYPE_CHECKING:`` blocks. Anything
    # inside such a block is fine because TYPE_CHECKING is False at
    # runtime.
    in_type_checking = False
    type_checking_indent = -1
    for raw_line in pre_def.splitlines():
        stripped = raw_line.lstrip()
        indent = len(raw_line) - len(stripped)

        if in_type_checking and indent <= type_checking_indent:
            in_type_checking = False

        if stripped.startswith("if TYPE_CHECKING"):
            in_type_checking = True
            type_checking_indent = indent
            continue

        if in_type_checking:
            continue

        if stripped.startswith(("import geopandas", "from geopandas")):
            raise AssertionError(
                f"Eager top-level geopandas import in geo.py: {raw_line!r}"
            )
        if stripped.startswith(("import shapely", "from shapely")):
            raise AssertionError(
                f"Eager top-level shapely import in geo.py: {raw_line!r}"
            )
