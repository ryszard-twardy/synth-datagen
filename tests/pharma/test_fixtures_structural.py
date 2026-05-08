"""Structural tests for the pharma test fixtures.

These tests run BEFORE ``geo.py`` exists — they validate the fixture
files themselves so that downstream tests in commits 5+ can rely on a
known-good input. No production code is exercised here.

Provenance contract from ``tests/fixtures/pharma/README.md``:
- All coords are simple decimals (multiples of 0.25).
- Institution names are invented; PLZ in the 99001–99099 range.
- AGS hierarchy: every Landkreis ``ags_2digit_parent`` exists in the
  Bundesländer set, and equals ``ags_5digit[:2]``.
- Hospitals CSV schema matches prompts/pharma/04_integration_notes.md §4.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pharma"

# Spec schema for the OSM hospitals CSV — 13 columns, locked.
EXPECTED_HOSPITAL_COLUMNS: tuple[str, ...] = (
    "osm_id",
    "osm_type",
    "name",
    "latitude",
    "longitude",
    "street",
    "city",
    "plz",
    "bundesland",
    "amenity",
    "healthcare",
    "beds",
    "operator_type",
)


def _load_geojson(name: str) -> dict:
    path = FIXTURE_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Bundesländer fixture
# ---------------------------------------------------------------------------


def test_bundeslaender_geojson_loadable() -> None:
    fc = _load_geojson("bundeslaender_test.geojson")
    assert fc["type"] == "FeatureCollection"
    assert isinstance(fc["features"], list)


def test_bundeslaender_three_features() -> None:
    fc = _load_geojson("bundeslaender_test.geojson")
    assert len(fc["features"]) == 3


def test_bundeslaender_required_properties() -> None:
    fc = _load_geojson("bundeslaender_test.geojson")
    for feat in fc["features"]:
        props = feat["properties"]
        assert "ags_2digit" in props
        assert "name" in props
        assert "population" in props
        assert isinstance(props["population"], int)
        assert props["population"] > 0
        assert len(props["ags_2digit"]) == 2


def test_bundeslaender_ags_unique() -> None:
    fc = _load_geojson("bundeslaender_test.geojson")
    ags = [f["properties"]["ags_2digit"] for f in fc["features"]]
    assert len(set(ags)) == len(ags), f"Duplicate Bundesland AGS: {ags}"


# ---------------------------------------------------------------------------
# Landkreise fixture
# ---------------------------------------------------------------------------


def test_landkreise_geojson_loadable() -> None:
    fc = _load_geojson("landkreise_test.geojson")
    assert fc["type"] == "FeatureCollection"


def test_landkreise_count_minimum_ten() -> None:
    """Engine downstream tests sample from this — need ≥ 10."""
    fc = _load_geojson("landkreise_test.geojson")
    assert len(fc["features"]) >= 10


def test_landkreise_ags_5digit_format() -> None:
    fc = _load_geojson("landkreise_test.geojson")
    for feat in fc["features"]:
        ags = feat["properties"]["ags_5digit"]
        assert isinstance(ags, str)
        assert len(ags) == 5
        assert ags.isdigit()


def test_landkreise_parent_ags_resolves_to_bundesland() -> None:
    """AGS hierarchy: every LK's ``ags_2digit_parent`` must exist in the
    Bundesländer set, AND must equal ``ags_5digit[:2]``."""
    bl_fc = _load_geojson("bundeslaender_test.geojson")
    lk_fc = _load_geojson("landkreise_test.geojson")
    bl_ags = {f["properties"]["ags_2digit"] for f in bl_fc["features"]}
    for feat in lk_fc["features"]:
        props = feat["properties"]
        parent = props["ags_2digit_parent"]
        five = props["ags_5digit"]
        assert parent in bl_ags, f"LK {five} has unknown parent {parent}"
        assert five[:2] == parent, (
            f"LK {five} parent {parent} disagrees with prefix {five[:2]}"
        )


def test_landkreise_ags_unique() -> None:
    fc = _load_geojson("landkreise_test.geojson")
    ags = [f["properties"]["ags_5digit"] for f in fc["features"]]
    assert len(set(ags)) == len(ags), f"Duplicate Landkreis AGS: {ags}"


def test_landkreise_population_sum_close_to_bundesland_population() -> None:
    """Sum of Landkreis populations within a Bundesland should equal the
    Bundesland's own population (synthetic fixture is exact)."""
    bl_fc = _load_geojson("bundeslaender_test.geojson")
    lk_fc = _load_geojson("landkreise_test.geojson")
    bl_pop = {
        f["properties"]["ags_2digit"]: f["properties"]["population"]
        for f in bl_fc["features"]
    }
    lk_sum: dict[str, int] = {}
    for feat in lk_fc["features"]:
        parent = feat["properties"]["ags_2digit_parent"]
        lk_sum[parent] = lk_sum.get(parent, 0) + feat["properties"]["population"]
    for ags, pop in bl_pop.items():
        assert lk_sum[ags] == pop, f"BL {ags} population {pop} != LK sum {lk_sum[ags]}"


# ---------------------------------------------------------------------------
# OSM hospitals CSV fixture
# ---------------------------------------------------------------------------


def test_hospitals_csv_required_columns() -> None:
    """Schema must match prompts/pharma/04_integration_notes.md §4."""
    df = pd.read_csv(FIXTURE_DIR / "osm_hospitals_DE_test.csv")
    assert tuple(df.columns) == EXPECTED_HOSPITAL_COLUMNS


def test_hospitals_csv_no_null_coordinates() -> None:
    df = pd.read_csv(FIXTURE_DIR / "osm_hospitals_DE_test.csv")
    assert df["latitude"].notna().all()
    assert df["longitude"].notna().all()


def test_hospitals_csv_minimum_rows() -> None:
    """Engine sub-mode filters need enough hospital + clinic rows to
    sample from."""
    df = pd.read_csv(FIXTURE_DIR / "osm_hospitals_DE_test.csv")
    assert len(df) >= 15


def test_hospitals_csv_acute_and_specialty_subsets_nonempty() -> None:
    """Acute-care sub-mode needs ``amenity=hospital``; specialty-care
    needs ``amenity=clinic`` (or ``healthcare=specialist``). Both
    subsets must be exercised."""
    df = pd.read_csv(FIXTURE_DIR / "osm_hospitals_DE_test.csv")
    assert (df["amenity"] == "hospital").sum() >= 5
    assert (df["amenity"] == "clinic").sum() >= 3


def test_hospitals_csv_beds_present_for_hospitals() -> None:
    """Acute-care filter is amenity=hospital with beds≥50. The fixture
    must give hospital rows a non-NULL bed count so the filter has
    something to keep."""
    df = pd.read_csv(FIXTURE_DIR / "osm_hospitals_DE_test.csv")
    hospitals = df[df["amenity"] == "hospital"]
    assert hospitals["beds"].notna().all()
    assert (hospitals["beds"] >= 50).all()


def test_hospitals_csv_plz_in_synthetic_range() -> None:
    """Provenance: PLZ values restricted to 99001–99099, a range
    Germany has never assigned, so even an accidental match against a
    real OSM dump is a non-collision."""
    df = pd.read_csv(FIXTURE_DIR / "osm_hospitals_DE_test.csv")
    plz_strs = df["plz"].astype(str)
    for plz in plz_strs:
        # Pad single-digit numbers in case pandas drops the leading zero.
        plz_int = int(plz)
        assert 99001 <= plz_int <= 99099, (
            f"PLZ {plz} outside synthetic range 99001-99099"
        )


def test_hospitals_csv_coords_within_fixture_bounding_box() -> None:
    """All hospital points must fall inside the synthetic bounding box
    (lat 50–53, lon 10–14) so spatial join always resolves."""
    df = pd.read_csv(FIXTURE_DIR / "osm_hospitals_DE_test.csv")
    assert df["latitude"].between(50.0, 53.0).all()
    assert df["longitude"].between(10.0, 14.0).all()


# ---------------------------------------------------------------------------
# Filesystem hygiene
# ---------------------------------------------------------------------------


def test_fixture_directory_total_size_under_100kb() -> None:
    """Hermetic fixtures should stay tiny so CI doesn't pay an I/O tax."""
    total = sum(p.stat().st_size for p in FIXTURE_DIR.iterdir() if p.is_file())
    assert total < 100 * 1024, f"Fixture directory is {total} bytes (>100 KB)"


def test_fixture_readme_present() -> None:
    """Provenance documentation is required."""
    assert (FIXTURE_DIR / "README.md").exists()
