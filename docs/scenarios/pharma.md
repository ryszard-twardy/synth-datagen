# Pharma — German Field-Sales scenario

A v0.3.0 8-table star schema modelling a German pharmaceutical
manufacturer's field-sales motion. Two sub-modes (`acute-care` for
hospitals, `specialty-care` for clinics + MVZ) target the unique
narrative of the [P7 GIS Territory Optimization
dashboard](https://github.com/ryszard-twardy) — acute-vs-specialty
channel imbalance across the 16 Bundesländer + ~401 Landkreise.

The pharma scenario depends on **caller-supplied** geographic data:
an [OSM](https://www.openstreetmap.org) hospital snapshot CSV
(license: ODbL) and the
[BKG VG250](https://gdz.bkg.bund.de) administrative-boundary
GeoJSONs (license: dl-de/by-2-0). `synth-datagen` does not bundle
either source — fetch them once into your consumer repo and pass the
paths via `--hospitals-csv` / `--bkg-bundeslaender` / `--bkg-landkreise`.

## Tables

8 tables, all CSV by default (Parquet support deferred to v0.3.x):

| Table | Kind | Default rows | Notes |
|---|---|---|---|
| `accounts` | dim | 850 acute / 850 specialty | OSM-sourced hospitals or clinics with imputed bed counts, AGS hierarchy, ownership, revenue |
| `sales_reps` | dim | 40 | German rep names, home location concentrated in Bayern + NRW + Baden-Württemberg per Pharmalotse |
| `territories` | dim | 4-18 | Multi-Landkreis territory groups with target revenue |
| `products` | dim | 25 acute / 18 specialty | PZN8 (BfArM-valid checksum) + WHO ATC level-5 codes |
| `orders` | fact | ~50K-200K | Pareto-distributed across accounts; log-normal frequency × amount |
| `rep_visits` | fact | ~5K-15K | Beta-distributed visit frequency, REQ-4 calibrated |
| `account_specialties` | bridge | 1-3 per account | Multi-specialty assignment with `is_primary` flag |
| `geographic_metadata` | meta | 1 row | Run-level summary + geo-lineage block (license attribution) |

`account_count` and `rep_count` are configurable via CLI flags.

## Sample command

```bash
synth-datagen pharma generate \
    --sub-mode acute-care \
    --hospitals-csv ./data/osm_hospitals_germany_20260601.csv \
    --bkg-bundeslaender ./data/de_bundeslaender_VG250.geojson \
    --bkg-landkreise   ./data/de_landkreise_VG250.geojson \
    --company-name "MediCorp" \
    --rep-count 40 --account-count 850 \
    --seed 20260601 \
    --output ./data/medicorp_acute \
    --benchmark-validation
```

A smoke-scale run (`--account-count 100`) finishes in well under a
second on Linux + Windows; macOS users without GDAL installed via
brew may see a delay during the first geopandas import.

## Sample output

```
data/medicorp_acute/
├── accounts.csv             sales_reps.csv         territories.csv
├── products.csv             orders.csv             rep_visits.csv
├── account_specialties.csv  geographic_metadata.csv
├── metadata.json            ← effective_config + rng_state_hash + geo_lineage + generated_at
├── geo_lineage.md           ← license attribution + dataset shape
└── benchmark_validation.md  ← only when --benchmark-validation set
```

## CLI design notes

The pharma sub-command sits at `synth-datagen pharma generate ...`
matching the `saas-v3 generate` idiom (sub-app + sub-subcommand).
This deviates from the spec's earlier flat-flag form
(`synth-datagen pharma --sub-mode ...`) — the deviation is
deliberate: the saas-v3 idiom is what shipped in v0.2.1, so pharma
mirrors the precedent rather than introducing a third surface.

The `--sub-mode` flag is mandatory and validated against the
`{acute-care, specialty-care}` literal set; `vertical-account-based`
(documented in early planning) is **not** a pharma sub-mode and
will be rejected with a Pydantic ValidationError. See the
[SaaS scenario page](saas.md#deferred-modes) for the SaaS
vertical-account-based status.

## Sub-modes

### `acute-care`

Hospitals (OSM `amenity=hospital`, beds ≥ 50). ATC mix dominated
by anti-infectives (J), antineoplastic + immunomodulating (L),
nervous-system (N), blood (B). Decision unit: hospital pharmacy
committee — long sales cycles, monthly bulk orders.

- Account count: 600-900 typical (`--account-count`).
- Archetypes: University, Maximalversorger, Schwerpunktversorger,
  Grundversorger.
- Bed count: log-normal mean=145, σ=0.85 (DESTATIS-anchored).
- Rep count: ~20 accounts per rep (default `--rep-count 40`).

### `specialty-care`

Specialty clinics + MVZ (OSM `amenity=clinic`). One primary ATC
group dominates per run (`--primary-atc`, defaults to L01 oncology;
also accepts L04 / S01 / D). Decision unit: specialist physician
— short cycles, weekly orders.

- Account count: 1500-2500 typical.
- Archetypes: Specialist, MVZ.
- Bed count: NULL (clinics aren't bed-counted).
- Rep count: ~30 accounts per rep (default `--rep-count 60`).

## Benchmark sources

Every distribution parameter cites a public source in
[`src/synth_datagen/pharma/benchmarks.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/pharma/benchmarks.py).
Re-validate annually against the latest releases:

| Source | URL | Used for |
|---|---|---|
| DESTATIS Krankenhausstatistik 2023 | <https://www.destatis.de/DE/Themes/Society-Environment/Health/Hospitals/> | Hospital counts, bed counts, ownership shares |
| PHAGRO Zahlen-Daten-Fakten 2024 | <https://www.phagro.de/zahlen-daten-fakten/> | Wholesale revenue, Rx share, regulated margin |
| IQVIA Marktbericht Classic 2022 | <https://www.iqvia.com/-/media/iqvia/pdfs/germany/library/publications/> | Hospital + retail channel splits |
| vfa Innovationsbilanz 2024 + Biotech-Report 2025 | <https://www.vfa.de/de/forschung-entwicklung/meilensteine-und-neueinfuehrungen> | New active substances, top-4 therapy areas |
| Pharmalotse Berufsbild Pharmareferent | <https://www.pharmalotse.de/berufsbild-pharmareferent/> | Field-force size, daily visit benchmarks |

### A note on federal arithmetic

Federal statistical sources may show small subtype-vs-total
arithmetic gaps due to reclassification timing. The DESTATIS 2023
publication, for instance, lists `TOTAL_HOSPITALS_DE = 1874` while
the sum of acute-care + psychiatric + day-surgery subtypes
reconciles to 1925 — the ~3 % overrun reflects facilities counted
in more than one subtype table (e.g. a Universitätsklinikum
publishing both an acute-care and a psychiatric department). The
pharma constants reflect literal cited values; tests use loose
envelopes that absorb such gaps without flake.

## Reproducibility

Pharma uses RNG salt `0x5DDA50000` (registered as `"pharma"` in
[`src/synth_datagen/rng.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/rng.py))
and 8 isolated child streams via
`make_rng(seed, "pharma").spawn(8)`:

```
accounts → reps → territories → orders → products
       → engagement → quality → regional
```

Spawn order is locked. Adding a new stream MUST append at the end;
the byte-stable contract for any prior seed depends on it. The
test [`test_make_pharma_streams_returns_eight_named_streams`](https://github.com/ryszard-twardy/synth-datagen/blob/main/tests/pharma/test_engine_smoke.py)
pins the names + count.

The same seed produces byte-identical CSVs across runs. Verified
by `scripts/baseline_diff.py` which captures both sub-modes
alongside retail/saas/fintech/logistics/saas_v3 from v0.3.0
forward.

## Validation pass

When `--benchmark-validation` is set, a v0.3.0 validation pass
runs after generation and writes `benchmark_validation.md`. Five
checks land in v0.3.0:

| Check | REQ | Hermetic fixture | Real BKG data |
|---|---|---|---|
| AGS hierarchy invariant | REQ-1 | runs | runs |
| BL population correlation (Spearman ρ > 0.7) | REQ-1 | skipped (n_BL=3) | skipped pending engine wiring |
| Revenue median in sub-mode band | REQ-3 | runs | runs |
| Visit frequency in sub-mode band | REQ-4 | runs | runs |
| Top-20 % revenue concentration | REQ-5 | runs | runs |
| Orders FK integrity | REQ-7 | runs | runs |

REQ-2 (ownership distribution) and REQ-6 (product catalog spread)
are deferred to v0.3.x — those need production-scale data to
assert meaningfully. See the
[CHANGELOG](../changelog.md#deferred-to-v03x) for the full list.

The pass exits non-zero when overall_status is `fail` (CSVs still
written for inspection — saas_v3 idiom). Run validation as a
CI gate or skip the flag for fast inner-loop generation.

## Loading recipes

- [BigQuery — pharma section](../recipes/bigquery-loading.md#pharma-eight-tables-with-spatial-clustering)

## Caveats & limitations

- **`[pharma]` extra required.** Install with
  `pip install 'synth-datagen[pharma]'`. The CLI fails fast with a
  friendly install hint when `geopandas` / `shapely` aren't
  available.
- **Tested on Linux + Windows.** macOS users may need to
  `brew install gdal` before `pip install` succeeds; geopandas's
  Linux + Windows wheels bundle GDAL but the macOS wheel pipeline
  was patchy at the time of v0.3.0 release.
- **Engine I/O contract.** `engine.generate()` is a pure function
  returning a dict of DataFrames. The CLI in
  [`src/synth_datagen/pharma/cli.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/pharma/cli.py)
  is the only writer.
- **No real BKG/OSM data committed.** The tests under
  `tests/fixtures/pharma/` are hand-authored synthetic stand-ins
  (3 BLs, 12 LKs, 20 hospitals); see
  [`tests/fixtures/pharma/README.md`](https://github.com/ryszard-twardy/synth-datagen/blob/main/tests/fixtures/pharma/README.md)
  for the provenance contract.

## Python API equivalent

```python
from pathlib import Path

from synth_datagen.pharma import engine
from synth_datagen.pharma.config import PharmaConfig

cfg = PharmaConfig(
    sub_mode="acute-care",
    hospitals_csv=Path("./data/osm_hospitals_germany_20260601.csv"),
    bkg_bundeslaender=Path("./data/de_bundeslaender_VG250.geojson"),
    bkg_landkreise=Path("./data/de_landkreise_VG250.geojson"),
    seed=20260601,
    account_count=850,
    rep_count=40,
    company_name="MediCorp",
)
tables = engine.generate(cfg)  # dict[str, pandas.DataFrame], 8 tables
# CLI handles serialization; engine itself does no file I/O.
```

The runnable example for the P7 GIS Territory project is at
[`examples/pharma_medicorp.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/examples/pharma_medicorp.py).
