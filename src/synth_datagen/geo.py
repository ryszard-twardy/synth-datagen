"""Shared German-administrative-geometry helpers (Phase 6 / v0.3.0).

Used by the pharma scenario today; written shared (top-level under
``synth_datagen``, not under ``pharma/``) because the AGS hierarchy
machinery is reusable for any future scenario that touches German
geography (logistics warehouse routing, retail catchment analysis).

## Optional dependency on geopandas

This module is imported by pharma code, which lives behind the optional
``[pharma]`` extra. To keep ``import synth_datagen.geo`` itself cheap
and non-fatal for users who haven't installed the extra, ALL geopandas
and shapely imports are lazy — performed inside the functions that
need them, not at module top. Functions that *don't* need them (notably
``haversine_km``) work without the extra installed at all.

Tests in ``tests/pharma/test_geo.py`` enforce this contract by reading
this module's source and asserting no eager top-level
``import geopandas`` / ``import shapely`` lines exist.

## CRS handling

Production callers pass real BKG VG250 GeoJSONs in EPSG:25832 (UTM
32N). Hospitals come from OSM in EPSG:4326 (WGS84). The loaders here
re-project every input to EPSG:4326 so spatial joins downstream are
consistent. The hermetic test fixtures are authored in EPSG:4326
already, so the reprojection is a no-op for them.

## AGS (Amtlicher Gemeindeschlüssel) hierarchy

- 2-digit AGS = Bundesland (e.g. ``09`` = Bayern).
- 5-digit AGS = Landkreis (e.g. ``09162`` = Stadt München).
- The first 2 digits of a Landkreis AGS equal its parent
  Bundesland AGS — the hierarchy is encoded in the data, no lookup
  table needed. ``validate_ags_hierarchy`` enforces this invariant.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    # Type-only imports; never executed at runtime, so the [pharma]
    # extra is not required to type-check or import this module.
    import geopandas as gpd  # noqa: F401


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _read_and_normalise_crs(geojson_path: Path) -> "gpd.GeoDataFrame":
    """Read a GeoJSON and re-project to EPSG:4326 if needed.

    GeoJSON specifies WGS84 as the default CRS, and ``pyogrio`` /
    ``fiona`` always populate ``gdf.crs`` on read for a well-formed
    file. So in practice the only branch that ever fires is the
    re-projection one (real BKG VG250 input is EPSG:25832).
    """
    import geopandas as gpd  # lazy

    gdf = gpd.read_file(geojson_path)
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def load_bundeslaender(geojson_path: Path) -> "gpd.GeoDataFrame":
    """Load a Bundesländer GeoJSON and re-project to EPSG:4326.

    Expected feature properties: ``ags_2digit`` (2-char string),
    ``name`` (str), ``population`` (int). Geometry: Polygon /
    MultiPolygon.

    Real BKG VG250 LAN files arrive in EPSG:25832 — this function
    re-projects to EPSG:4326 unconditionally so downstream joins
    against OSM (also 4326) are consistent.
    """
    return _read_and_normalise_crs(geojson_path)


def load_landkreise(geojson_path: Path) -> "gpd.GeoDataFrame":
    """Load a Landkreise GeoJSON and re-project to EPSG:4326.

    Expected feature properties: ``ags_5digit`` (5-char digit string),
    ``ags_2digit_parent`` (2-char digit string equal to
    ``ags_5digit[:2]``), ``name`` (str), ``population`` (int).
    """
    return _read_and_normalise_crs(geojson_path)


def load_osm_hospitals(csv_path: Path) -> pd.DataFrame:
    """Read an OSM hospital snapshot CSV.

    Schema documented in
    ``prompts/pharma/04_integration_notes.md`` §4. We don't validate
    every column here — that's the engine's job — but we ensure the
    coordinates parse as floats so downstream spatial joins succeed.
    """
    df = pd.read_csv(csv_path)
    return df


# ---------------------------------------------------------------------------
# AGS hierarchy validation
# ---------------------------------------------------------------------------


def validate_ags_hierarchy(
    landkreise: "pd.DataFrame | gpd.GeoDataFrame",
    bundeslaender: "pd.DataFrame | gpd.GeoDataFrame",
) -> None:
    """Raise ``ValueError`` if the AGS hierarchy invariant is broken.

    Two checks:

    1. Every Landkreis ``ags_2digit_parent`` must appear in the
       Bundesländer ``ags_2digit`` column (no orphans).
    2. Every Landkreis must satisfy
       ``ags_5digit[:2] == ags_2digit_parent`` (no prefix mismatch).

    Both checks raise ``ValueError`` with a message containing keywords
    ``orphan``, ``parent``, ``prefix``, ``mismatch``, or ``hierarchy``
    so callers (and tests) can match on intent.
    """
    bl_set = set(bundeslaender["ags_2digit"].astype(str))
    parents = landkreise["ags_2digit_parent"].astype(str)
    five = landkreise["ags_5digit"].astype(str)

    orphans = parents[~parents.isin(bl_set)]
    if not orphans.empty:
        sample = orphans.head(5).tolist()
        raise ValueError(
            f"AGS hierarchy violation: {len(orphans)} Landkreis row(s) "
            f"have orphan parent AGS not in Bundesländer set. Sample: "
            f"{sample}. Fix the parent BKG release or refresh the "
            f"snapshot."
        )

    mismatches_mask = five.str.slice(0, 2) != parents
    if mismatches_mask.any():
        bad_rows = landkreise.loc[mismatches_mask, ["ags_5digit", "ags_2digit_parent"]]
        sample = bad_rows.head(5).to_dict("records")
        raise ValueError(
            f"AGS hierarchy violation: prefix mismatch on "
            f"{int(mismatches_mask.sum())} Landkreis row(s) — "
            f"ags_5digit[:2] != ags_2digit_parent. Sample: {sample}."
        )


# ---------------------------------------------------------------------------
# Spatial join
# ---------------------------------------------------------------------------


def spatial_join_to_landkreis(
    points: pd.DataFrame,
    landkreise: "gpd.GeoDataFrame",
    *,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
) -> pd.Series:
    """Return a ``Series[str]`` of Landkreis AGS for each input point.

    Input ``points`` is a plain DataFrame with ``lat_col`` /
    ``lon_col`` columns (defaults: ``latitude``/``longitude``).
    Output is positionally aligned with ``points``: row *i* of the
    returned Series is the AGS for ``points.iloc[i]``. Points outside
    every Landkreis polygon return ``NaN``.

    Implementation uses ``geopandas.sjoin(predicate='within')`` which
    handles boundary cases consistently and is R-tree-indexed under
    the hood — fast enough for real-scale input (~3000 OSM rows ×
    ~401 Landkreis polygons completes in well under a second).
    """
    import geopandas as gpd  # lazy
    from shapely.geometry import Point  # lazy

    geometries = [Point(lon, lat) for lat, lon in zip(points[lat_col], points[lon_col])]
    points_gdf = gpd.GeoDataFrame(
        {"_synth_idx": range(len(points))},
        geometry=geometries,
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(
        points_gdf,
        landkreise[["ags_5digit", "geometry"]],
        how="left",
        predicate="within",
    )
    # ``sjoin`` may return more rows than input if a point sits on a
    # boundary shared by two polygons. Deduplicate by keeping the
    # first match per input row, then re-index against the input
    # range so the output is positionally aligned and contains exactly
    # ``len(points)`` rows.
    deduped = joined.drop_duplicates(subset="_synth_idx", keep="first")
    deduped = deduped.set_index("_synth_idx").sort_index()
    ags = deduped["ags_5digit"].reindex(range(len(points)))
    ags.index = points.index
    return ags


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in kilometres.

    Pure-stdlib implementation — no numpy, no geopandas, no shapely.
    Uses the mean Earth radius 6371 km, standard for synth-datagen's
    distance calculations elsewhere.
    """
    earth_radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_km * c
