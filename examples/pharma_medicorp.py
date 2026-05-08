"""MediCorp pharma scenario example for the P7 GIS Territory dashboard.

Generates an acute-care German pharmaceutical sales dataset for a
fictional manufacturer ('MediCorp') via the engine's pure-function
form and prints summary stats + benchmark-validation result to stdout.

To write CSVs + metadata.json + geo_lineage.md to disk, use the
equivalent ``synth-datagen pharma generate ... --output ./out/medicorp``
CLI form documented below.

This is the runnable demo for the v0.3.0 pharma scenario. It documents
the production workflow (caller-supplied real BKG VG250 + OSM data) and
falls back to the project's hermetic mini-fixtures when those files
aren't available locally — so the script always runs without you having
to pre-fetch anything.

Run from repo root:

    pip install -e ".[pharma]"
    python examples/pharma_medicorp.py

Equivalent CLI form (with real production data):

    synth-datagen pharma generate \\
        --sub-mode acute-care \\
        --hospitals-csv data/osm_hospitals_germany_20260601.csv \\
        --bkg-bundeslaender data/de_bundeslaender_VG250.geojson \\
        --bkg-landkreise   data/de_landkreise_VG250.geojson \\
        --company-name "MediCorp" \\
        --rep-count 40 --account-count 850 \\
        --seed 20260601 \\
        --output ./out/pharma_medicorp \\
        --benchmark-validation

To use real data instead of the hermetic fixtures, set
``PHARMA_REAL_GEO_DIR`` to a directory containing:

  - osm_hospitals_germany.csv      (Overpass API export, ODbL)
  - bundeslaender_VG250.geojson    (BKG, dl-de/by-2-0)
  - landkreise_VG250.geojson       (BKG, dl-de/by-2-0)

Sources:
  - OSM Overpass: https://overpass-api.de — query for amenity=hospital
    or amenity=clinic in Germany; export as CSV with the schema
    documented in ``prompts/pharma/04_integration_notes.md`` Section 4.
  - BKG VG250: https://gdz.bkg.bund.de — VG250-EW dataset, GeoJSON
    format, EPSG:25832 native (geo.py reprojects to 4326 on load).

synth-datagen does NOT bundle either source — license attribution is
the consumer's responsibility per ODbL / dl-de/by-2-0.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HERMETIC_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "pharma"


def _resolve_input_paths() -> tuple[Path, Path, Path, str]:
    """Return ``(hospitals_csv, bl_geojson, lk_geojson, mode)``.

    ``mode`` is 'real' when ``PHARMA_REAL_GEO_DIR`` env var points at a
    directory with the three expected files, else 'hermetic' (falling
    back to the test fixtures so the script always runs).
    """
    real_dir_str = os.environ.get("PHARMA_REAL_GEO_DIR")
    if real_dir_str:
        real_dir = Path(real_dir_str).expanduser().resolve()
        candidate = (
            real_dir / "osm_hospitals_germany.csv",
            real_dir / "bundeslaender_VG250.geojson",
            real_dir / "landkreise_VG250.geojson",
        )
        if all(p.exists() for p in candidate):
            return (*candidate, "real")
        missing = [p.name for p in candidate if not p.exists()]
        print(
            f"[pharma_medicorp] PHARMA_REAL_GEO_DIR={real_dir} is set but "
            f"missing files: {missing}. Falling back to hermetic fixtures."
        )

    return (
        HERMETIC_FIXTURE_DIR / "osm_hospitals_DE_test.csv",
        HERMETIC_FIXTURE_DIR / "bundeslaender_test.geojson",
        HERMETIC_FIXTURE_DIR / "landkreise_test.geojson",
        "hermetic",
    )


def main() -> None:
    # Lazy import — fail with a clear message if [pharma] extra is
    # missing, mirroring the CLI's friendly install-hint behaviour.
    try:
        from synth_datagen.pharma import engine, validate
        from synth_datagen.pharma.config import PharmaConfig
    except ImportError as exc:
        print(
            "[pharma_medicorp] Missing dependency: "
            f"{exc}\n"
            'Install with:  pip install -e ".[pharma]"'
        )
        raise SystemExit(1)

    hospitals_csv, bl_geojson, lk_geojson, mode = _resolve_input_paths()

    # Real BKG data has 16 BLs; tune account_count up. Hermetic fixture
    # has 3 BLs and 12 LKs — keep the run small so it stays fast.
    if mode == "real":
        account_count = 850
        rep_count = 40
        seed = 20260601
    else:
        account_count = 200
        rep_count = 15
        seed = 20260601

    cfg = PharmaConfig(
        sub_mode="acute-care",
        hospitals_csv=hospitals_csv,
        bkg_bundeslaender=bl_geojson,
        bkg_landkreise=lk_geojson,
        seed=seed,
        company_name="MediCorp",
        rep_count=rep_count,
        account_count=account_count,
        data_quality="medium",
        benchmark_validation=True,
    )

    print(f"[pharma_medicorp] mode={mode}")
    print(f"[pharma_medicorp] inputs from: {hospitals_csv.parent}")
    print(
        f"[pharma_medicorp] generating: sub_mode=acute-care "
        f"seed={seed} accounts={account_count} reps={rep_count}"
    )

    tables = engine.generate(cfg)

    # Summary stats — mirrors what the P7 GIS Territory dashboard
    # expects for its 'data quality' page.
    accounts = tables["accounts"]
    orders = tables["orders"]
    geo_meta = tables["geographic_metadata"].iloc[0]

    print()
    print("=== MediCorp acute-care dataset summary ===")
    print(f"  Accounts:          {len(accounts):>6}")
    print(f"  Sales reps:        {len(tables['sales_reps']):>6}")
    print(f"  Territories:       {len(tables['territories']):>6}")
    print(f"  Products:          {len(tables['products']):>6}")
    print(f"  Orders:            {len(orders):>6}")
    print(f"  Rep visits:        {len(tables['rep_visits']):>6}")
    print(f"  Specialties:       {len(tables['account_specialties']):>6}")
    print()
    print(f"  Bundesländer:      {int(geo_meta['bundesland_count']):>6}")
    print(f"  Landkreise:        {int(geo_meta['landkreis_count']):>6}")
    print(f"  LK coverage:       {float(geo_meta['landkreis_coverage_pct']):>6.2f}%")
    print()
    print(f"  Median revenue:    €{accounts['annual_revenue'].median():>10,.0f}")
    print(f"  Total revenue:     €{accounts['annual_revenue'].sum():>10,.0f}")

    # Run benchmark validation and surface the result line.
    result = validate.validate(cfg, tables)
    summary = result.summary()
    print()
    print("=== Benchmark validation ===")
    print(
        f"  overall: {result.overall_status.upper()}  "
        f"(pass={summary['pass']} fail={summary['fail']} "
        f"warn={summary['warn']} skip={summary['skip']})"
    )

    if mode == "hermetic":
        print()
        print(
            "[pharma_medicorp] Tip: set PHARMA_REAL_GEO_DIR to a dir "
            "with real BKG VG250 + OSM data to run a production-scale "
            "MediCorp dataset for the P7 GIS Territory dashboard."
        )


if __name__ == "__main__":
    main()
