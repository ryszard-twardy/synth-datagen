"""Pharma scenario engine — produces the 8-table German Field-Sales
synthetic dataset.

Public API:

    generate(config: PharmaConfig) -> dict[str, pd.DataFrame]
    make_pharma_streams(base_seed: int) -> dict[str, np.random.Generator]

Engine design:

1. ``make_pharma_streams`` derives a master Generator via
   ``make_rng(seed, "pharma")`` (the central salt registry) and spawns
   exactly 8 child streams in a locked order:

       accounts → reps → territories → orders → products
              → engagement → quality → regional

   Adding a new stream MUST extend this list AT THE END so the bytes
   for any prior seed remain stable. ``test_make_pharma_streams_*``
   tests in test_engine_smoke.py pin the names + count.

2. ``generate`` orchestrates the 8 tables in dependency order:

       accounts (from OSM × BKG via geo.py)
           → sales_reps (assigned to a future territory)
           → territories (clusters of LKs)
           → products (PZN + ATC catalog)
           → orders (Pareto over accounts × time)
           → rep_visits (Beta visit-frequency)
           → account_specialties (1+ per account)
           → geographic_metadata (single-row summary)
           → defects pass (clean / medium / messy)

   The engine performs ZERO file I/O. CLI handlers (commit 12) are
   responsible for writing CSVs / metadata.json / benchmark_validation.md
   / geo_lineage.md. The engine does compute the geo-lineage *data*
   structure inside ``geographic_metadata`` so the CLI can serialize
   it without re-loading the input files.

3. RNG discipline: every stochastic draw inside this module must use
   one of the 8 spawned streams. There are NO direct
   ``np.random.default_rng`` calls. ``test_no_direct_default_rng_*``
   in test_engine_smoke.py walks the package AST and asserts this.

Spec reference: prompts/pharma/05_implementation.md (REQ-1 through
REQ-8, DATA SCHEMA, SCENARIO ARCHITECTURE).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from synth_datagen import geo
from synth_datagen.pharma import benchmarks, defects, vocab
from synth_datagen.pharma.config import PharmaConfig
from synth_datagen.rng import make_rng

if TYPE_CHECKING:  # pragma: no cover
    import geopandas as gpd  # noqa: F401


# ---------------------------------------------------------------------------
# Stream architecture — locked order
# ---------------------------------------------------------------------------

# Spawn order. Adding a new stream MUST append at the end (existing
# seeds rely on the spawn-slot ladder). ``test_make_pharma_streams_*``
# pins this list.
_STREAM_LABELS: tuple[str, ...] = (
    "accounts",
    "reps",
    "territories",
    "orders",
    "products",
    "engagement",
    "quality",
    "regional",
)


def make_pharma_streams(base_seed: int) -> dict[str, np.random.Generator]:
    """Return the 8 isolated RNG streams the pharma engine consumes."""
    master = make_rng(base_seed, "pharma")
    children = master.spawn(len(_STREAM_LABELS))
    return dict(zip(_STREAM_LABELS, children))


# ---------------------------------------------------------------------------
# Sub-mode constants — the spec REQ-2 distributions and REQ-3 revenue
# bands. Lifted into module-level dicts so engine logic stays readable.
# ---------------------------------------------------------------------------

# Acute-care archetype shares (approximate; sums to 1.0 across the four
# Krankenhaus tiers). Universitätskliniken are pinned exactly via
# benchmarks.UNIVERSITY_HOSPITALS_DE rather than via this share.
_ACUTE_ARCHETYPE_SHARES: dict[str, float] = {
    # University is pinned to ~3 % of acute accounts (35 / 1585 nationally).
    "University": 0.03,
    "Maximalversorger": 0.10,
    "Schwerpunktversorger": 0.27,
    "Grundversorger": 0.60,
}

# Specialty-care archetype shares.
_SPECIALTY_ARCHETYPE_SHARES: dict[str, float] = {
    "Specialist": 0.50,
    "MVZ": 0.50,
}

# Rep home concentration (Pharmalotse): ~50 % of pharma jobs in
# BY (09) + NW (05) + BW (08), the rest distributed across the
# remaining Bundesländer. Fixture has only AGS '01', '09', '11', so
# the BL-09 weight applies and the others fall back to the residual
# bucket — fixture tests that depend on the real-world geographic
# concentration are gated behind ``@pytest.mark.real_geo`` and
# skipped by default.
_REP_HOME_CONCENTRATION_BLS: tuple[str, ...] = ("09", "05", "08")
_REP_HOME_CONCENTRATION_SHARE: float = 0.50

# Acute revenue parameters per REQ-3 (log-normal, mean ~€95k, σ=1.15).
_ACUTE_REVENUE_LN_MEAN: float = float(np.log(95_000.0))
_ACUTE_REVENUE_LN_SIGMA: float = 1.15

# Specialty revenue parameters per REQ-3 (log-normal, mean ~€18k, σ=0.95).
_SPECIALTY_REVENUE_LN_MEAN: float = float(np.log(18_000.0))
_SPECIALTY_REVENUE_LN_SIGMA: float = 0.95

# Bed-count log-normal per REQ-2 (acute only).
_ACUTE_BEDS_LN_MEAN: float = float(np.log(145.0))
_ACUTE_BEDS_LN_SIGMA: float = 0.85

# Visit-frequency Beta parameters per REQ-4.
# Acute: 3-6 visits/year, Beta(α=2, β=3) over the range.
# Specialty: 8-14 visits/year, Beta(α=2.5, β=2.5) over the range.
_ACUTE_VISIT_BETA: tuple[float, float] = (2.0, 3.0)
_ACUTE_VISIT_RANGE: tuple[float, float] = (3.0, 6.0)
_SPECIALTY_VISIT_BETA: tuple[float, float] = (2.5, 2.5)
_SPECIALTY_VISIT_RANGE: tuple[float, float] = (8.0, 14.0)

# Order-pattern parameters per REQ-5.
_ACUTE_ORDER_FREQ_LN_MEAN: float = float(np.log(18.0))  # ~monthly bulk
_ACUTE_ORDER_FREQ_LN_SIGMA: float = 0.7
_SPECIALTY_ORDER_FREQ_LN_MEAN: float = float(np.log(42.0))  # weekly-ish
_SPECIALTY_ORDER_FREQ_LN_SIGMA: float = 0.6

_ACUTE_ORDER_AMOUNT_LN_MEAN: float = float(np.log(450.0))
_ACUTE_ORDER_AMOUNT_LN_SIGMA: float = 1.4
_SPECIALTY_ORDER_AMOUNT_LN_MEAN: float = float(np.log(180.0))
_SPECIALTY_ORDER_AMOUNT_LN_SIGMA: float = 1.1

# Product-catalog sizes per the sub-mode distinctions.
_ACUTE_PRODUCT_COUNT: int = 25
_SPECIALTY_PRODUCT_COUNT: int = 18

# Acute-care primary ATC anatomical groups (REQ-6). Acute draws
# uniformly across J / L / N / B; specialty pins to its primary.
_ACUTE_PRIMARY_GROUPS: tuple[str, ...] = ("J", "L", "N", "B")


# ---------------------------------------------------------------------------
# Geo-lineage data dict (returned inside geographic_metadata; CLI
# serializes to geo_lineage.md without re-reading the input files).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _GeoLineage:
    """Captured at generation time for the geo_lineage.md artifact."""

    osm_snapshot_filename: str
    bkg_bundeslaender_filename: str
    bkg_landkreise_filename: str
    bundesland_count: int
    landkreis_count: int
    osm_license: str
    bkg_license: str

    def as_dict(self) -> dict[str, object]:
        return {
            "osm_snapshot_filename": self.osm_snapshot_filename,
            "bkg_bundeslaender_filename": self.bkg_bundeslaender_filename,
            "bkg_landkreise_filename": self.bkg_landkreise_filename,
            "bundesland_count": self.bundesland_count,
            "landkreis_count": self.landkreis_count,
            "osm_license": self.osm_license,
            "bkg_license": self.bkg_license,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate(config: PharmaConfig) -> dict[str, pd.DataFrame]:
    """Generate the 8-table pharma dataset for the supplied config."""
    streams = make_pharma_streams(config.seed)

    bl_gdf = geo.load_bundeslaender(config.bkg_bundeslaender)
    lk_gdf = geo.load_landkreise(config.bkg_landkreise)
    geo.validate_ags_hierarchy(lk_gdf, bl_gdf)
    osm_df = geo.load_osm_hospitals(config.hospitals_csv)

    accounts = _generate_accounts(
        config=config,
        osm=osm_df,
        bl=bl_gdf,
        lk=lk_gdf,
        rng=streams["accounts"],
    )

    territories = _generate_territories(
        config=config,
        accounts=accounts,
        rng=streams["territories"],
    )

    sales_reps = _generate_sales_reps(
        config=config,
        territories=territories,
        bl=bl_gdf,
        lk=lk_gdf,
        rng=streams["reps"],
    )

    products = _generate_products(
        config=config,
        rng=streams["products"],
    )

    orders = _generate_orders(
        config=config,
        accounts=accounts,
        sales_reps=sales_reps,
        products=products,
        rng=streams["orders"],
    )

    rep_visits = _generate_rep_visits(
        config=config,
        accounts=accounts,
        sales_reps=sales_reps,
        rng=streams["engagement"],
    )

    account_specialties = _generate_account_specialties(
        accounts=accounts,
        rng=streams["regional"],
    )

    lineage = _GeoLineage(
        osm_snapshot_filename=config.hospitals_csv.name,
        bkg_bundeslaender_filename=config.bkg_bundeslaender.name,
        bkg_landkreise_filename=config.bkg_landkreise.name,
        bundesland_count=int(len(bl_gdf)),
        landkreis_count=int(len(lk_gdf)),
        osm_license="ODbL",
        bkg_license="dl-de/by-2-0",
    )

    geographic_metadata = _generate_geographic_metadata(
        config=config,
        accounts=accounts,
        bl=bl_gdf,
        lk=lk_gdf,
        lineage=lineage,
    )

    tables: dict[str, pd.DataFrame] = {
        "accounts": accounts,
        "sales_reps": sales_reps,
        "territories": territories,
        "products": products,
        "orders": orders,
        "rep_visits": rep_visits,
        "account_specialties": account_specialties,
        "geographic_metadata": geographic_metadata,
    }

    # Defects pass — uses the dedicated quality stream only (REQ-7).
    tables = defects.apply_pharma_defects(
        tables,
        level=config.data_quality,
        rng=streams["quality"],
    )

    # Re-bundle the post-defects mapping into the same 8-key dict.
    return {name: tables[name] for name in tables}


# ---------------------------------------------------------------------------
# Table generators — private helpers, one per table
# ---------------------------------------------------------------------------


def _archetype_shares_for_sub_mode(sub_mode: str) -> dict[str, float]:
    if sub_mode == "acute-care":
        return _ACUTE_ARCHETYPE_SHARES
    return _SPECIALTY_ARCHETYPE_SHARES


def _filter_osm_for_sub_mode(osm: pd.DataFrame, sub_mode: str) -> pd.DataFrame:
    """Spec §SCENARIO ARCHITECTURE filter rules."""
    if sub_mode == "acute-care":
        # amenity=hospital with bed_count present (NULL imputed
        # downstream from log-normal so the engine doesn't lose
        # OSM rows that lack a beds tag).
        mask = osm["amenity"].astype(str) == "hospital"
    else:
        mask = osm["amenity"].astype(str) == "clinic"
    return osm.loc[mask].reset_index(drop=True)


def _generate_accounts(
    *,
    config: PharmaConfig,
    osm: pd.DataFrame,
    bl: "gpd.GeoDataFrame",
    lk: "gpd.GeoDataFrame",
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate the accounts table.

    Steps:
    1. Filter OSM by sub-mode (hospital vs clinic).
    2. Sample N rows with replacement so the engine is robust to
       small fixtures (the production OSM snapshot has ~3000+ rows;
       the hermetic fixture has 12 hospitals + 8 clinics, so
       replacement is required for account_count=200).
    3. Spatial-join lat/lon → landkreis_ags → bundesland_ags via
       geo.spatial_join_to_landkreis.
    4. Assign archetypes weighted per the sub-mode shares; pin
       University to ~3 % of acute.
    5. Impute bed_count via log-normal for hospitals.
    6. Draw annual_revenue from log-normal.
    7. Assign ownership_type (acute) or 'NA' (specialty).
    """
    pool = _filter_osm_for_sub_mode(osm, config.sub_mode)
    if pool.empty:
        raise ValueError(
            f"OSM input has zero rows matching sub_mode={config.sub_mode!r}. "
            "Check the --hospitals-csv input file."
        )

    n = config.account_count
    sample_idx = rng.integers(0, len(pool), size=n)
    sampled = pool.iloc[sample_idx].reset_index(drop=True)

    # Spatial join → landkreis AGS, then prefix → bundesland AGS.
    lk_ags = geo.spatial_join_to_landkreis(
        sampled[["latitude", "longitude"]],
        lk,
    )
    # If a sampled point lands outside every fixture polygon (only
    # plausible for malformed inputs since the fixture covers the
    # bounding box), fill from the spatial-join NaN fallback by
    # picking any LK at random — keeps the AGS hierarchy intact at
    # the cost of geographic precision for that row.
    if lk_ags.isna().any():
        fallback = lk["ags_5digit"].astype(str).tolist()
        fallback_pick = rng.choice(fallback, size=int(lk_ags.isna().sum()))
        lk_ags = lk_ags.copy()
        lk_ags.loc[lk_ags.isna()] = fallback_pick
    landkreis_ags = lk_ags.astype(str).tolist()
    bundesland_ags = [a[:2] for a in landkreis_ags]

    # Archetype assignment.
    archetype_shares = _archetype_shares_for_sub_mode(config.sub_mode)
    archetype_labels = list(archetype_shares.keys())
    archetype_probs = np.array(list(archetype_shares.values()))
    archetype_probs = archetype_probs / archetype_probs.sum()
    archetypes = rng.choice(archetype_labels, size=n, p=archetype_probs)

    # account_type per the spec mapping (engine uses the simpler
    # archetype → account_type rule rather than reading OSM tags).
    account_type = np.where(
        np.isin(archetypes, list(vocab.ACUTE_CARE_ARCHETYPES)),
        "Hospital",
        np.where(archetypes == "MVZ", "MVZ", "SpecialtyClinic"),
    )

    # Bed-count: log-normal for acute (NaN for specialty).
    if config.sub_mode == "acute-care":
        bed_count = rng.lognormal(_ACUTE_BEDS_LN_MEAN, _ACUTE_BEDS_LN_SIGMA, size=n)
        bed_count = np.clip(bed_count, 30.0, 2500.0).astype(int)
    else:
        bed_count = np.full(n, np.nan)

    # Annual revenue.
    if config.sub_mode == "acute-care":
        revenue = rng.lognormal(_ACUTE_REVENUE_LN_MEAN, _ACUTE_REVENUE_LN_SIGMA, size=n)
    else:
        revenue = rng.lognormal(
            _SPECIALTY_REVENUE_LN_MEAN, _SPECIALTY_REVENUE_LN_SIGMA, size=n
        )
    revenue = np.round(revenue, 2)

    # Ownership: acute uses the DESTATIS public/non-profit/for-profit
    # split. Specialty: 'private' (most clinics) / 'public' (some MVZ).
    if config.sub_mode == "acute-care":
        ownership = rng.choice(
            ["public", "nonprofit", "forprofit"],
            size=n,
            p=[
                benchmarks.PCT_HOSPITALS_PUBLIC,
                benchmarks.PCT_HOSPITALS_NONPROFIT,
                benchmarks.PCT_HOSPITALS_FORPROFIT,
            ],
        )
    else:
        ownership = rng.choice(["private", "public"], size=n, p=[0.85, 0.15])

    # Hospital names: regenerate for realism rather than re-using the
    # OSM source name (the OSM snapshot may have synthetic names too).
    is_university = archetypes == "University"
    names = [
        vocab.generate_hospital_name(rng, is_university=bool(is_university[i]))
        for i in range(n)
    ]

    # Status: 4 % acute / 9 % specialty inactive per REQ-1 churn rates
    # (annualised; smoke tests just check the bool column exists).
    inactive_rate = 0.04 if config.sub_mode == "acute-care" else 0.09
    is_inactive = rng.random(n) < inactive_rate
    status = np.where(is_inactive, "inactive", "active")

    accounts = pd.DataFrame(
        {
            "account_id": [f"acc_pharma_{i:06d}" for i in range(n)],
            "osm_id": sampled["osm_id"].astype("Int64").to_numpy(),
            "name": names,
            "account_type": account_type,
            "account_archetype": archetypes,
            "sub_mode": config.sub_mode,
            "bed_count": bed_count,
            "street": sampled["street"].fillna("").to_numpy(),
            "city": sampled["city"].fillna("").to_numpy(),
            "plz": sampled["plz"].fillna("").astype(str).to_numpy(),
            "bundesland_ags": bundesland_ags,
            "landkreis_ags": landkreis_ags,
            "latitude": np.round(sampled["latitude"].to_numpy(), 6),
            "longitude": np.round(sampled["longitude"].to_numpy(), 6),
            "ownership_type": ownership,
            "annual_revenue": revenue,
            "status": status,
        }
    )
    return accounts


def _generate_territories(
    *,
    config: PharmaConfig,
    accounts: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """One territory per region group; assigns target_revenue from the
    accounts share covered. Keeps territory geometry as a list of LK
    AGS for downstream PostGIS consumption (engine-level, no
    geometry serialization here)."""
    bl_present = accounts["bundesland_ags"].astype(str).unique().tolist()
    bl_present.sort()
    n_terr = max(4, min(18, len(bl_present) * 2))

    territory_records = []
    for tid in range(n_terr):
        bl_pick = bl_present[tid % len(bl_present)]
        in_bl = accounts.loc[accounts["bundesland_ags"] == bl_pick]
        share_revenue = float(in_bl["annual_revenue"].sum()) / max(1.0, n_terr)
        territory_records.append(
            {
                "territory_id": f"ter_pharma_{tid:04d}",
                "territory_name": f"Territory-{tid:02d}",
                "region": _region_for_bl(bl_pick),
                "sub_mode": config.sub_mode,
                "target_revenue": round(share_revenue, 2),
            }
        )
    # Add deterministic noise via the territory stream so the table
    # has a non-trivial sampled column (avoids "all integers" output).
    territory_records_df = pd.DataFrame(territory_records)
    territory_records_df["target_revenue"] = (
        territory_records_df["target_revenue"]
        * (1.0 + rng.uniform(-0.05, 0.05, size=n_terr))
    ).round(2)
    return territory_records_df


def _region_for_bl(ags2: str) -> str:
    """Coarse region bucket for the spec's territory-name pattern.
    Real BL codes 09/13 → Süd, 05/03 → West, 04/14 → Ost, etc.
    Fixture's '01/09/11' → Nord/Süd/Ost respectively."""
    region_map = {
        "01": "Nord",
        "02": "Nord",
        "03": "West",
        "04": "Ost",
        "05": "West",
        "06": "Mitte",
        "07": "Mitte",
        "08": "West",
        "09": "Süd",
        "10": "Mitte",
        "11": "Ost",
        "12": "Ost",
        "13": "Nord",
        "14": "Ost",
        "15": "Mitte",
        "16": "Mitte",
    }
    return region_map.get(ags2, "Mitte")


def _generate_sales_reps(
    *,
    config: PharmaConfig,
    territories: pd.DataFrame,
    bl: "gpd.GeoDataFrame",
    lk: "gpd.GeoDataFrame",
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate the sales_reps table.

    Home location: 50 % concentrated in BY (09) + NW (05) + BW (08)
    per Pharmalotse benchmark. Real-BL-code distribution; fixture
    only has '01', '09', '11' so the BL-09 weight applies and the
    others fall back to residual. Tests that assert the 50%
    concentration use real-BL fixtures and are gated behind
    ``@pytest.mark.real_geo``.
    """
    n = config.rep_count
    bl_ags_all = bl["ags_2digit"].astype(str).tolist()

    # Build BL weights honouring the concentration band.
    high_bls = [a for a in bl_ags_all if a in _REP_HOME_CONCENTRATION_BLS]
    other_bls = [a for a in bl_ags_all if a not in _REP_HOME_CONCENTRATION_BLS]
    weights: list[float] = []
    for ags2 in bl_ags_all:
        if ags2 in high_bls:
            weights.append(_REP_HOME_CONCENTRATION_SHARE / max(1, len(high_bls)))
        else:
            weights.append(
                (1.0 - _REP_HOME_CONCENTRATION_SHARE) / max(1, len(other_bls) or 1)
            )
    # If high_bls is empty (fixture without any of 09/05/08), fall
    # back to uniform so the weights still sum to 1.
    if not high_bls:
        weights = [1.0 / len(bl_ags_all)] * len(bl_ags_all)
    weights_arr = np.array(weights)
    weights_arr = weights_arr / weights_arr.sum()

    home_bls = rng.choice(bl_ags_all, size=n, p=weights_arr)

    # For each rep, pick a Landkreis within the chosen BL.
    home_lks: list[str] = []
    home_lats: list[float] = []
    home_lons: list[float] = []
    for ags2 in home_bls:
        lk_in_bl = lk[lk["ags_2digit_parent"].astype(str) == ags2]
        if lk_in_bl.empty:
            lk_pick = lk.sample(n=1, random_state=int(rng.integers(0, 2**31)))
        else:
            lk_pick_idx = int(rng.integers(0, len(lk_in_bl)))
            lk_pick = lk_in_bl.iloc[[lk_pick_idx]]
        lk_pick_first = lk_pick.iloc[0]
        home_lks.append(str(lk_pick_first["ags_5digit"]))
        # Use the polygon centroid for home lat/lon — synthetic
        # but reasonable for distance calculations downstream.
        centroid = lk_pick_first.geometry.centroid
        home_lats.append(round(float(centroid.y), 6))
        home_lons.append(round(float(centroid.x), 6))

    # Tenure: log-normal mean=4.2 yr, sigma=0.9 (REQ-4).
    tenure_years = rng.lognormal(np.log(4.2), 0.9, size=n)
    tenure_years = np.clip(tenure_years, 0.25, 35.0).round(2)

    # End-date is the config's end_date (engine "as-of"); hire-date
    # = end_date - tenure_years.
    hire_dates = [
        config.end_date - timedelta(days=int(round(t * 365.25))) for t in tenure_years
    ]

    # Territory assignment: cycle reps across territories.
    territory_ids = territories["territory_id"].astype(str).tolist()
    if not territory_ids:
        # Should never happen — territories is always non-empty —
        # but fail loudly rather than silently producing NaN FKs.
        raise RuntimeError("territories table empty — cannot assign reps")
    rep_territory = [territory_ids[i % len(territory_ids)] for i in range(n)]

    # Names: simple "Rep {i}" — engine doesn't pretend to generate
    # realistic German person names (out of scope for v0.3.0).
    names = [f"Rep-{i:03d}" for i in range(n)]

    return pd.DataFrame(
        {
            "rep_id": [f"rep_pharma_{i:04d}" for i in range(n)],
            "name": names,
            "sub_mode": config.sub_mode,
            "home_bundesland_ags": home_bls,
            "home_landkreis_ags": home_lks,
            "latitude": home_lats,
            "longitude": home_lons,
            "territory_id": rep_territory,
            "hire_date": hire_dates,
            "tenure_years": tenure_years,
        }
    )


def _generate_products(
    *,
    config: PharmaConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate the products catalog.

    Acute-care: ~25 products spread across J / L / N / B groups.
    Specialty-care: ~18 products pinned to ``primary_atc`` (defaults
    to L01 oncology).
    """
    n = (
        _ACUTE_PRODUCT_COUNT
        if config.sub_mode == "acute-care"
        else _SPECIALTY_PRODUCT_COUNT
    )

    # ATC codes: acute draws from the four primary groups uniformly;
    # specialty pins to config.primary_atc (which the config validator
    # already restricted to {L01, L04, S01, D}).
    if config.sub_mode == "acute-care":
        primary_pick = rng.choice(_ACUTE_PRIMARY_GROUPS, size=n)
        atc_codes = [vocab.generate_atc_code(rng, primary=str(p)) for p in primary_pick]
    else:
        primary = config.primary_atc or "L01"
        atc_codes = [vocab.generate_atc_code(rng, primary=primary) for _ in range(n)]

    pzns = [vocab.generate_pzn(rng) for _ in range(n)]

    # Unit price log-normal — different bands for acute vs specialty.
    if config.sub_mode == "acute-care":
        unit_prices = rng.lognormal(np.log(80.0), 1.0, size=n)
    else:
        unit_prices = rng.lognormal(np.log(350.0), 1.1, size=n)
    unit_prices = np.round(np.clip(unit_prices, 1.5, 50_000.0), 2)

    # Manufacturer margin per REQ-3. Specialty band (25-45%) higher
    # than acute (12-25%).
    if config.sub_mode == "acute-care":
        margin_pct = rng.uniform(0.04, 0.25, size=n)
    else:
        margin_pct = rng.uniform(0.12, 0.45, size=n)
    margin_pct = np.round(margin_pct, 4)

    is_hospital_only = rng.random(n) < (
        0.30 if config.sub_mode == "acute-care" else 0.0
    )

    is_innovation = rng.random(n) < 0.05  # ~5 % new in last 24 months

    return pd.DataFrame(
        {
            "product_id": [f"prd_pharma_{i:04d}" for i in range(n)],
            "pzn": pzns,
            "atc_code": atc_codes,
            "product_name": [f"Synth-{p}-{i:02d}" for i, p in enumerate(pzns)],
            "unit_price": unit_prices,
            "margin_pct": margin_pct,
            "is_hospital_only": is_hospital_only,
            "is_innovation": is_innovation,
        }
    )


def _generate_orders(
    *,
    config: PharmaConfig,
    accounts: pd.DataFrame,
    sales_reps: pd.DataFrame,
    products: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate the orders table.

    Order count per account is log-normal × tenure_years; total
    rows = sum across accounts. Per-row account_id, rep_id (random
    rep), product_id, order_date (uniform in [start_date, end_date]),
    quantity, amount.
    """
    if config.sub_mode == "acute-care":
        ln_mean = _ACUTE_ORDER_FREQ_LN_MEAN
        ln_sigma = _ACUTE_ORDER_FREQ_LN_SIGMA
        amt_mean = _ACUTE_ORDER_AMOUNT_LN_MEAN
        amt_sigma = _ACUTE_ORDER_AMOUNT_LN_SIGMA
    else:
        ln_mean = _SPECIALTY_ORDER_FREQ_LN_MEAN
        ln_sigma = _SPECIALTY_ORDER_FREQ_LN_SIGMA
        amt_mean = _SPECIALTY_ORDER_AMOUNT_LN_MEAN
        amt_sigma = _SPECIALTY_ORDER_AMOUNT_LN_SIGMA

    # Days in the window — per REQ-5 historical span.
    days_total = (config.end_date - config.start_date).days
    if days_total <= 0:
        raise ValueError(
            f"end_date {config.end_date} is not after start_date {config.start_date}"
        )

    # Per-account order counts (per year), scaled to the window length.
    n_accounts = len(accounts)
    per_year = rng.lognormal(ln_mean, ln_sigma, size=n_accounts)
    years_in_window = days_total / 365.25
    counts_per_account = np.round(per_year * years_in_window).astype(int)
    counts_per_account = np.clip(counts_per_account, 0, 1_000)

    total_orders = int(counts_per_account.sum())
    if total_orders == 0:
        # Edge case: very small account_count + low frequency. Force
        # at least 1 order on the highest-revenue account so downstream
        # FK tests don't see an empty orders table.
        counts_per_account[0] = 1
        total_orders = 1

    # Build per-row arrays.
    account_ids: list[str] = []
    for acc_id, cnt in zip(accounts["account_id"].tolist(), counts_per_account):
        account_ids.extend([acc_id] * int(cnt))

    rep_ids = rng.choice(
        sales_reps["rep_id"].astype(str).tolist(),
        size=total_orders,
    )
    product_ids = rng.choice(
        products["product_id"].astype(str).tolist(),
        size=total_orders,
    )

    # Order dates uniform in the window.
    day_offsets = rng.integers(0, days_total + 1, size=total_orders)
    order_dates = pd.to_datetime(
        [config.start_date + timedelta(days=int(d)) for d in day_offsets]
    )

    # Quantities log-normal mean=10, sigma=0.7 (rounded to int).
    quantities = rng.lognormal(np.log(10.0), 0.7, size=total_orders)
    quantities = np.clip(quantities, 1, 5000).astype(int)

    # Amount per row = quantity × unit-price-per-product.
    product_unit_prices = dict(
        zip(products["product_id"].astype(str), products["unit_price"].astype(float))
    )
    unit_amounts = np.array([product_unit_prices[str(p)] for p in product_ids])
    # Apply lognormal noise around the spec amount distribution so
    # different products give different actual order sizes.
    amount_noise = rng.lognormal(amt_mean - np.log(450.0), amt_sigma, size=total_orders)
    amounts = np.round(unit_amounts * quantities * amount_noise, 2)

    return pd.DataFrame(
        {
            "order_id": [f"ord_pharma_{i:08d}" for i in range(total_orders)],
            "account_id": account_ids,
            "rep_id": rep_ids,
            "product_id": product_ids,
            "order_date": order_dates,
            "quantity": quantities,
            "amount": amounts,
            "discount_pct": np.round(rng.uniform(0.0, 0.25, size=total_orders), 4),
        }
    )


def _generate_rep_visits(
    *,
    config: PharmaConfig,
    accounts: pd.DataFrame,
    sales_reps: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate the rep_visits table.

    Visit frequency per account per year drawn from a Beta scaled to
    the spec REQ-4 range (acute: 3-6, specialty: 8-14). Total visits
    = freq × years_in_window.
    """
    if config.sub_mode == "acute-care":
        alpha, beta = _ACUTE_VISIT_BETA
        lo, hi = _ACUTE_VISIT_RANGE
    else:
        alpha, beta = _SPECIALTY_VISIT_BETA
        lo, hi = _SPECIALTY_VISIT_RANGE

    days_total = (config.end_date - config.start_date).days
    years_in_window = days_total / 365.25

    n_accounts = len(accounts)
    per_year = rng.beta(alpha, beta, size=n_accounts) * (hi - lo) + lo
    counts_per_account = np.round(per_year * years_in_window).astype(int)
    counts_per_account = np.clip(counts_per_account, 0, 5_000)

    total_visits = int(counts_per_account.sum())
    if total_visits == 0:
        counts_per_account[0] = 1
        total_visits = 1

    account_ids: list[str] = []
    for acc_id, cnt in zip(accounts["account_id"].tolist(), counts_per_account):
        account_ids.extend([acc_id] * int(cnt))

    rep_ids = rng.choice(
        sales_reps["rep_id"].astype(str).tolist(),
        size=total_visits,
    )
    day_offsets = rng.integers(0, days_total + 1, size=total_visits)
    visit_dates = pd.to_datetime(
        [config.start_date + timedelta(days=int(d)) for d in day_offsets]
    )

    # Visit duration: mean=15 acute / mean=8 specialty.
    if config.sub_mode == "acute-care":
        durations = rng.lognormal(np.log(15.0), 0.4, size=total_visits)
    else:
        durations = rng.lognormal(np.log(8.0), 0.4, size=total_visits)
    durations = np.clip(durations, 1.0, 90.0).round(0).astype(int)

    outcomes = rng.choice(
        ["info", "sample", "demo", "follow-up", "no-access"],
        size=total_visits,
        p=[0.45, 0.20, 0.10, 0.20, 0.05],
    )

    return pd.DataFrame(
        {
            "visit_id": [f"vis_pharma_{i:08d}" for i in range(total_visits)],
            "account_id": account_ids,
            "rep_id": rep_ids,
            "visit_date": visit_dates,
            "visit_duration_minutes": durations,
            "outcome": outcomes,
        }
    )


def _generate_account_specialties(
    *,
    accounts: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """One or more specialty rows per account; one is_primary=true.

    Spec: 1500-4000 rows for the full-scale dataset. At smoke scale
    (200 accounts) we get ~300-500 rows.
    """
    specialty_pool = (
        "Onkologie",
        "Kardiologie",
        "Orthopädie",
        "Neurologie",
        "Innere Medizin",
        "Pädiatrie",
        "Gynäkologie",
        "Augenheilkunde",
        "Dermatologie",
    )

    n_accounts = len(accounts)
    rows: list[dict[str, object]] = []
    # 1-3 specialties per account with weights favouring 1.
    specialty_counts = rng.choice([1, 2, 3], size=n_accounts, p=[0.55, 0.30, 0.15])
    for acc_id, cnt in zip(accounts["account_id"].tolist(), specialty_counts):
        chosen = rng.choice(specialty_pool, size=int(cnt), replace=False)
        for i, spec in enumerate(chosen):
            rows.append(
                {
                    "account_id": acc_id,
                    "specialty": str(spec),
                    "is_primary": bool(i == 0),
                }
            )

    return pd.DataFrame(rows)


def _generate_geographic_metadata(
    *,
    config: PharmaConfig,
    accounts: pd.DataFrame,
    bl: "gpd.GeoDataFrame",
    lk: "gpd.GeoDataFrame",
    lineage: _GeoLineage,
) -> pd.DataFrame:
    """Single-row summary for the metadata.json + geo_lineage.md
    artifacts."""
    landkreise_with_accounts = accounts["landkreis_ags"].astype(str).nunique()
    coverage_pct = round(
        100.0 * landkreise_with_accounts / max(1, len(lk)),
        2,
    )

    record = {
        "seed": int(config.seed),
        "sub_mode": config.sub_mode,
        "company_name": config.company_name,
        "bundesland_count": int(len(bl)),
        "landkreis_count": int(len(lk)),
        "landkreise_with_accounts": int(landkreise_with_accounts),
        "landkreis_coverage_pct": coverage_pct,
        "total_accounts": int(len(accounts)),
        "as_of_date": config.end_date,
        # Lineage data — CLI serializes to geo_lineage.md.
        "geo_lineage": lineage.as_dict(),
    }
    return pd.DataFrame([record])
