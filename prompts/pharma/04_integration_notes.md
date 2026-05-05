# synth-datagen Pharma Field Sales — Integration Notes
## v1.0 — How the Pharma scenario fits into post-refactor architecture

> **Companion document to `Coding_Agent_Prompt_synth_datagen_Pharma.md`.** This is the "how it lives in the codebase" view; the coding agent prompt is the "how to build it" view. Read this BEFORE starting the Pharma scenario implementation. This assumes Phases 1–4 of the synth-datagen audit/refactor (`synth_datagen_audit_workflow.md`) are complete and the SaaS scenario extension (`Coding_Agent_Prompt_synth_datagen_SaaS.md`) is implemented.

---

## 1. Position in build sequence

```
[NOW]  P1 Kupferkanne (Pages 2–6 + drillthrough + NovyPro publish)
   ↓
synth-datagen Phase 1: Audit (1–2h agent + 30min review)
   ↓
synth-datagen Phase 2: Refactor (4–6h agent + 1h review)        ← src layout, Pydantic, RNG factory
   ↓
synth-datagen Phase 3: Tests (4–6h agent + 30min review)
   ↓
synth-datagen Phase 4: Docs (2–3h agent + 30min review)
   ↓
SaaS extension: plg-usage-based + vertical-account-based         ← per Coding_Agent_Prompt_SaaS.md
   ↓
★ Pharma Field Sales scenario: acute-care + specialty-care      ← THIS DOCUMENT + Coding_Agent_Prompt_Pharma.md
   ↓
Maven Supply Chain / Candy warm-up (PostGIS practice, 4–5 days)
   ↓
P2 SaaS Dashboard (Promptforge, ~10–14 days)
   ↓
P7 GIS Territory Dashboard build
   ↓
P14 RFEDA Account Health Scorecard
```

**Why Pharma comes after SaaS extension and before P2/P7 dashboards:** The SaaS extension establishes the sub-mode pattern (`plg-usage-based` vs `vertical-account-based`) that Pharma mirrors (`acute-care` vs `specialty-care`). Once Pharma is coded and tested, the user has all data engines ready and can build dashboards without context-switching back to Python.

---

## 2. Architectural fit with post-refactor structure

The post-refactor target structure (from `synth_datagen_audit_workflow.md` Phase 2) looks like this. Pharma additions are marked with `★`:

```
synth-datagen/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── src/synth_datagen/
│   ├── __init__.py
│   ├── cli.py                          (Typer entry point — add `pharma` subcommand)
│   ├── config.py                       (Pydantic models — add PharmaConfig + sub-mode configs)
│   ├── rng.py                          (RNG factory — add 0xPHA50000 base salt)
│   ├── distributions.py                (Beta/Pareto/lognormal helpers — likely no changes)
│   ├── quality.py                      (shared quality injection — likely no changes)
│   ├── docs.py                         (auto-doc generation — extend for pharma schema)
│   ├── geo.py                          ★ NEW: shared geo helpers (haversine, AGS hierarchy lookups)
│   ├── scenarios/
│   │   ├── __init__.py
│   │   ├── _base.py                    (Scenario protocol — unchanged)
│   │   ├── retail.py
│   │   ├── saas/
│   │   │   ├── __init__.py
│   │   │   ├── _common.py
│   │   │   ├── plg_usage_based.py
│   │   │   └── vertical_account_based.py
│   │   ├── fintech.py
│   │   ├── logistics.py
│   │   └── pharma/                     ★ NEW
│   │       ├── __init__.py             ★ exports the pharma scenario entry point
│   │       ├── _common.py              ★ shared logic between sub-modes (geo lookup, AGS hierarchy)
│   │       ├── acute_care.py           ★ sub-mode A: hospitals, bulk orders, longer cycles
│   │       └── specialty_care.py       ★ sub-mode B: specialty clinics, smaller frequent orders
│   └── benchmarks/
│       ├── retail.py
│       ├── saas.py
│       ├── fintech.py
│       ├── logistics.py
│       └── pharma.py                   ★ NEW: industry benchmark constants for German pharma
├── tests/
│   ├── conftest.py
│   ├── test_rng.py
│   ├── test_distributions.py
│   ├── test_reproducibility.py
│   ├── scenarios/
│   │   ├── test_retail.py
│   │   ├── test_saas_plg.py
│   │   ├── test_saas_vertical.py
│   │   ├── test_fintech.py
│   │   ├── test_logistics.py
│   │   ├── test_pharma_acute.py        ★ NEW
│   │   └── test_pharma_specialty.py    ★ NEW
│   └── property/
│       └── test_invariants.py          (extend with pharma invariants)
└── examples/
    ├── retail_quickstart.py
    ├── saas_promptforge.py
    ├── fintech_demo.py
    └── pharma_medicorp.py              ★ NEW: example for P7 GIS Territory project
```

**Net new files in synth-datagen for Pharma:** ~7–8 source files, ~2–3 test files, 1 example, 1 benchmark constants module. A new shared module `geo.py` is justified because hierarchical geo lookups (PLZ → Landkreis → Bundesland via AGS) will be needed in any future scenario that uses German geographic data (e.g., logistics warehouse routing).

---

## 3. RNG stream architecture

Following the established XOR-salt + spawn pattern from SaaS:

```python
# src/synth_datagen/rng.py — add the Pharma master salt
PHARMA_MASTER_SALT = 0x5DDA50000  # NEW

# Inside src/synth_datagen/scenarios/pharma/_common.py
import numpy as np
from synth_datagen.rng import PHARMA_MASTER_SALT

def make_pharma_rng_streams(base_seed: int) -> dict[str, np.random.Generator]:
    """Create isolated RNG streams for Pharma scenario.

    Sub-streams use spawn() to ensure adding new logic doesn't shift
    state for existing logic. Cf. SaaS pattern in scenarios/saas/_common.py.
    """
    pharma_master = np.random.default_rng(seed=base_seed ^ PHARMA_MASTER_SALT)
    streams = pharma_master.spawn(8)
    return {
        "accounts":     streams[0],   # account selection from OSM, plan_tier assignment
        "reps":         streams[1],   # rep home location, hire_date, tenure
        "territories":  streams[2],   # territory boundary generation, target revenue
        "orders":       streams[3],   # order timing, quantities, product mix
        "products":     streams[4],   # product catalog, pricing, ATC classification
        "engagement":   streams[5],   # rep visit frequency, call notes
        "quality":      streams[6],   # data quality injection (NULL, dupes, format errors)
        "regional":     streams[7],   # geographic clustering noise, density variations
    }
```

**Key invariant:** Adding a new stream MUST extend the spawn count and be appended at the END of the list. Inserting a stream in the middle would shift downstream RNG state and break backward compatibility for all prior seeds. This is enforced via test in `test_pharma_acute.py::test_stream_count_stable`.

**Salt choice rationale:** `0x5DDA50000` reads as "PHA50000" in hex (matching the SaaS convention `0x5AA50000`). Choose any unused 32-bit space; the only requirement is uniqueness across scenarios.

---

## 4. External dependency: OSM hospital snapshot

**Decision (confirmed in planning session):** OSM hospital fetch lives OUTSIDE synth-datagen. Pharma scenario takes a snapshot CSV as input. This keeps synth-datagen a pure data generator with no runtime network dependencies.

**Workflow:**

```
[ Repo: gis-territory-optimization (P7 GIS Territory) ]
├── scripts/
│   └── fetch_osm_hospitals.py          ← runs Overpass query, writes CSV
├── data/
│   └── osm_hospitals_germany_20260601.csv   ← committed snapshot, dated
│   └── osm_hospitals_LICENSE.txt        ← ODbL attribution

         ↓ user runs synth-datagen with --hospitals-csv pointing here

[ synth-datagen pharma scenario ]
synth-datagen pharma \
    --sub-mode acute-care \
    --hospitals-csv ../gis-territory-optimization/data/osm_hospitals_germany_20260601.csv \
    --bkg-bundeslaender data/de_bundeslaender_VG250.geojson \
    --bkg-landkreise   data/de_landkreise_VG250.geojson \
    --seed 20260601 \
    --output-dir ./data/medicorp_acute
```

**Pydantic config validation** (in `config.py`):

```python
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

class PharmaConfig(BaseModel):
    """Configuration for Pharma Field Sales scenarios."""
    sub_mode: Literal["acute-care", "specialty-care"]
    hospitals_csv: Path = Field(description="OSM hospital snapshot CSV (lat/lng/name/type)")
    bkg_bundeslaender: Path = Field(description="BKG VG250 Bundesländer GeoJSON")
    bkg_landkreise: Path = Field(description="BKG VG250 Landkreise GeoJSON")
    company_name: str = "MediCorp"
    rep_count: int = Field(default=40, ge=10, le=200)
    account_count: int = Field(default=850, ge=100, le=3000)
    start_date: date = Field(default=date(2023, 1, 1))
    end_date: date = Field(default=date(2026, 6, 30))
    target_quota_attainment: float = Field(default=0.92, ge=0.5, le=1.5)
    seed: int
    data_quality: Literal["clean", "medium", "messy"] = "medium"

    @field_validator("hospitals_csv", "bkg_bundeslaender", "bkg_landkreise")
    @classmethod
    def must_exist(cls, p: Path) -> Path:
        if not p.exists():
            raise ValueError(f"Required input file not found: {p}")
        return p
```

**Required schema for hospitals CSV input** (this is what `fetch_osm_hospitals.py` must produce):

| Column | Type | Description |
|--------|------|-------------|
| `osm_id` | int | OSM node/way ID |
| `osm_type` | str | "node" or "way" |
| `name` | str | Hospital name from OSM |
| `latitude` | float | WGS84 |
| `longitude` | float | WGS84 |
| `street` | str | Address (may be NULL) |
| `city` | str | City name (may be NULL) |
| `plz` | str | German postal code (may be NULL) |
| `bundesland` | str | Bundesland name (may be NULL — synth-datagen will resolve via spatial join) |
| `amenity` | str | "hospital", "clinic", "doctors" (OSM tag) |
| `healthcare` | str | OSM healthcare:speciality tag (may be NULL) |
| `beds` | int | OSM `beds` tag if present (mostly NULL — synth-datagen will impute) |
| `operator_type` | str | OSM `operator:type` if present (public/private/...) |

The Pharma scenario:
1. Reads the CSV
2. Performs spatial join against BKG Landkreise/Bundesländer to fill missing geographic fields
3. Filters to hospitals matching the sub-mode (acute-care: amenity=hospital with beds; specialty-care: amenity=clinic OR healthcare=specialist)
4. Samples N accounts according to `account_count` and the geographic density model
5. Generates synthetic accounts table with imputed `annual_revenue`, `bed_count`, `specialty_focus`, `account_archetype` etc.

---

## 5. Geographic hierarchy: AGS-based two-level analysis

**Decision (confirmed in planning session):** Two admin levels, Bundesländer (16) and Landkreise (~401), via BKG VG250 open data.

**Data flow:**

```
BKG VG250 ZIP (vg250_lan.geojson + vg250_krs.geojson)
       ↓
   geo.py loads + parses + validates
       ↓
   Returns:
   - bundeslaender_df:  16 rows  (ags_2digit, name, geometry, population)
   - landkreise_df:    ~401 rows  (ags_5digit, ags_2digit_parent, name, geometry, population)
       ↓
   Pharma scenario uses for:
   - Spatial join: account.lat,lng → landkreis_ags → bundesland_ags (via parent FK)
   - Density sampling: weighted by Landkreis population
   - Output schema: account.bundesland_ags + account.landkreis_ags as denormalized columns
```

**AGS (Amtlicher Gemeindeschlüssel) hierarchy:**
- 2-digit AGS = Bundesland (e.g., `09` = Bayern)
- 5-digit AGS = Landkreis (e.g., `09162` = Stadt München; `09184` = Landkreis München)
- The first 2 digits of a Landkreis AGS == the parent Bundesland AGS. Hierarchy is encoded in the data; no manual mapping needed.

**Output denormalization rationale:** The `accounts` table emitted by the Pharma scenario should include BOTH `bundesland_ags` and `landkreis_ags` as columns (precomputed by spatial join during generation). This means downstream SQL doesn't need PostGIS functions for simple roll-ups — just `GROUP BY bundesland_ags`. PostGIS is still used for distance calculations and coverage gaps in the GIS scenario, but every basic aggregation works on plain columns. This is consistent with the principle "do the spatial join once, at generation time".

---

## 6. Sub-mode differentiation

The two Pharma sub-modes mirror the SaaS pattern. They share `_common.py` (account generation skeleton, geographic resolution, quality injection) but diverge on:

| Dimension | `acute-care` | `specialty-care` |
|-----------|--------------|------------------|
| **Account type** | Hospitals (amenity=hospital, ≥50 beds) | Specialty clinics (amenity=clinic OR healthcare=specialist), small bed count or none |
| **Account count target** | ~600–900 (limited by hospital count in DE) | ~1,500–2,500 (more clinics than hospitals) |
| **Order size distribution** | Log-normal mean=€8,500, sigma=0.9 (bulk procurement) | Log-normal mean=€1,200, sigma=1.1 (smaller orders) |
| **Order frequency** | Lower (bulk monthly/quarterly) | Higher (weekly/biweekly) |
| **Sales cycle** | Long (formulary committee, hospital pharmacy approval) | Short (clinical decision, direct prescriber) |
| **Product mix** | Hospital-only injectables, IV products, ATC group J/L/N (anti-infectives, oncology, neurology) | Specialty-focused (one ATC primary group: oncology OR rheumatology OR ophthalmology) |
| **Margin%** | Lower (hospital pricing pressure, AMNOG impact) | Higher (specialty premium pricing) |
| **Decision unit** | Hospital pharmacy committee (multi-stakeholder) | Specialist physician (single-stakeholder) |
| **Rep call frequency** | 3–6 visits/year per account | 8–14 visits/year per account |
| **Coverage gap dynamics** | Driven by: hospital density × bed count threshold | Driven by: specialty density × patient catchment area |

**Why this differentiation matters for the dashboard:** P7 GIS Territory dashboard can show "acute vs specialty channel imbalance" — e.g., "MediCorp is over-indexed on acute care in Bayern but under-served in specialty care across the entire Eastern region." That narrative is impossible with a single-mode generator.

---

## 7. Tests required (extending Phase 3 framework)

The `synth_datagen_audit_workflow.md` Phase 3 prompt (test hardening) establishes the test pattern. For Pharma:

### Reproducibility test (P0 critical)
```python
def test_pharma_acute_reproducibility():
    """Same seed → identical output."""
    out1 = pharma.generate(sub_mode="acute-care", seed=42, account_count=300, ...)
    out2 = pharma.generate(sub_mode="acute-care", seed=42, account_count=300, ...)
    assert out1.equals(out2)
```

### Stream isolation test (P0 critical)
```python
def test_pharma_stream_isolation_quality_doesnt_shift_geo():
    """Changing data_quality should not shift account/territory generation."""
    base = pharma.generate(sub_mode="acute-care", seed=42, data_quality="clean", ...)
    msy  = pharma.generate(sub_mode="acute-care", seed=42, data_quality="messy", ...)
    # account_id, lat, lng, bundesland_ags, landkreis_ags should be IDENTICAL
    # only quality-injected fields (NULL rates, dupes) differ
    assert base["accounts"][["account_id","latitude","longitude","bundesland_ags","landkreis_ags"]].equals(
        msy["accounts"][["account_id","latitude","longitude","bundesland_ags","landkreis_ags"]]
    )
```

### Stream count stability test (prevents regression)
```python
def test_pharma_stream_count_stable():
    """Adding new RNG streams must extend, not insert. This test pins the count."""
    streams = make_pharma_rng_streams(base_seed=42)
    assert list(streams.keys()) == [
        "accounts", "reps", "territories", "orders",
        "products", "engagement", "quality", "regional",
    ]  # if you change this list, document the version bump
```

### Geographic plausibility tests
```python
def test_pharma_acute_density_correlates_with_population():
    """Hospital account density should correlate with Bundesland population."""
    out = pharma.generate(sub_mode="acute-care", seed=42, account_count=850, ...)
    accounts_per_bundesland = out["accounts"].groupby("bundesland_ags").size()
    # Spearman correlation with population — should be > 0.7
    correlation = compute_population_correlation(accounts_per_bundesland)
    assert correlation > 0.7

def test_pharma_landkreis_aggregation_sums_to_bundesland():
    """Sum of accounts across Landkreise of a Bundesland equals total accounts in that Bundesland."""
    out = pharma.generate(...)
    by_lk = out["accounts"].groupby("landkreis_ags").size().reset_index()
    # Extract first 2 chars of AGS as parent
    by_lk["bundesland_ags"] = by_lk["landkreis_ags"].str[:2]
    by_bl_from_lk = by_lk.groupby("bundesland_ags")["count"].sum()
    by_bl_direct = out["accounts"].groupby("bundesland_ags").size()
    assert by_bl_from_lk.equals(by_bl_direct)
```

### Benchmark validation tests (REQ-X enforcement)
See `Coding_Agent_Prompt_synth_datagen_Pharma.md` for the full REQ list. Each numbered REQ corresponds to a test in `test_pharma_*.py`.

---

## 8. Quality injection — Pharma-specific anti-patterns

The shared `quality.py` module covers generic patterns (NULL injection, duplicate rows, timestamp inconsistency). Pharma adds these scenario-specific quality issues to `_common.py`:

| Issue | Frequency (medium) | Realistic source |
|-------|-------------------|------------------|
| Hospital name spelling variants | 0.4% of accounts | Multiple OSM/Krankenhausverzeichnis source merges |
| PLZ format inconsistency (4-digit vs 5-digit, with/without leading 0) | 0.6% of accounts | Legacy CRM imports from pre-1993 era |
| Bundesland name vs ISO code mismatch ("Bayern" / "BY" / "Bavaria") | 0.3% of accounts | Multilingual CRM exports |
| Negative quantities in returns (legitimate but easy to filter incorrectly) | 1.1% of orders | Hospital pharmacy returns process |
| Order date misaligned with rep visit date by ±90 days (delayed entry) | 0.8% of orders | Late CRM entry in field |
| Account → rep assignment changes mid-order (reassignment events not propagated) | 0.5% of orders | Territory realignment legacy data |
| Duplicate ATC code with old vs new PZN | 0.3% of products | PZN renumbering events |
| Coordinates rounded to 3 decimals vs 6 decimals (inconsistent precision) | 1.0% of accounts | Multiple ETL sources merging |

Messy mode multiplies all rates by 4×; clean mode is exact.

---

## 9. Output artifacts (Pharma adds 1 file beyond the SaaS template)

Per `Coding_Agent_Prompt_synth_datagen_SaaS.md` Section "Output Artifacts", scenarios emit 7 files. Pharma emits 8:

1. CSV/Parquet data files (8 tables — see Pharma coding agent prompt Section "Data Schema")
2. `data_dictionary.md` — every column documented
3. `metadata.json` — generation parameters, seed, RNG state hashes, benchmark validation results
4. `benchmark_validation.md` — generated metrics vs DESTATIS / IQVIA / vfa benchmarks
5. `expected_findings.md` — pre-computed insights (e.g., "Bayern should show 22–26% of total revenue")
6. `schema.sql` — BigQuery DDL with clustering keys
7. `load_to_bigquery.sh` — `bq load` convenience script
8. `geo_lineage.md` ★ NEW — documents OSM snapshot date, BKG vintage, AGS schema version, license attribution (ODbL for OSM, dl-de/by-2-0 for BKG). This is required for portfolio honesty and license compliance.

---

## 10. Portfolio narrative — what this gives the user

After this scenario is done, the user can tell this story in interviews:

> "I have a synthetic data engine that powers five distinct portfolio projects: retail RFM (Kupferkanne), SaaS PLG metrics, SaaS account health scoring, payment funnel, and pharma field force optimization. Each scenario is calibrated against published industry benchmarks — I don't generate cartoon data. The pharma scenario, for example, anchors hospital counts to DESTATIS Krankenhausstatistik, wholesale margins to PHAGRO, and acute-vs-specialty channel dynamics to IQVIA DKM benchmarks. The whole engine is open source on GitHub with property-based tests via Hypothesis and CI on three Python versions."

That's a senior-level story. Most juniors say "I downloaded a Kaggle dataset and built a dashboard." The user says "I built the engine that simulates an industry, then built dashboards on top of it."

---

## 11. Risk register (Pharma-specific additions to audit workflow risks)

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| OSM Overpass API returns inconsistent results between snapshot dates (boundary changes, hospital closures) | High over time | Medium | Snapshot dated CSV committed to repo. Refresh annually with explicit version bump. |
| BKG VG250 vintage mismatch (Landkreis boundary changes, e.g., 2021 reform) | Medium | Low | Pin to specific BKG release year in `geo_lineage.md`. Document re-fetch procedure. |
| German hospital landscape continuing to consolidate (1,874 → fewer in coming years per current reform) | Medium | Low | Synthetic data is a snapshot; document the implied "as-of date" in `metadata.json`. |
| PLZ data quality from OSM is poor (NULL rate ~30% on minor entries) | High | Medium | Spatial join via lat/lng is primary; PLZ is denormalized helper only. |
| Hospital `beds` tag in OSM is sparse (~70% NULL) | High | Medium | Impute via Statistical model: `beds ~ LogNormal(μ, σ)` calibrated to DESTATIS averages by Bundesland and ownership type. |
| Two sub-modes in single PR creates large code review surface | Medium | Low | Implement `_common.py` first, then `acute_care.py`, then `specialty_care.py` as 3 separate commits. Each commit has TDD pair. |
| Backward compat breaks for SaaS/retail when adding `geo.py` shared module | Low | High | Run baseline diff (per Phase 2 protocol) on retail+saas+fintech+logistics with seed=42 BEFORE and AFTER adding `geo.py`. Empty diff required. |

---

## 12. What goes into v0.3.0 release (post-Pharma)

After Pharma is implemented and tested, the synth-datagen repo gets a v0.3.0 tag. CHANGELOG entry:

```markdown
## [0.3.0] — YYYY-MM-DD

### Added
- Pharma scenario with two sub-modes: `acute-care` and `specialty-care`
- Calibrated to German pharmaceutical market: DESTATIS Krankenhausstatistik, PHAGRO wholesale data, IQVIA DKM, vfa innovation data
- New shared module `geo.py` for German administrative hierarchy (AGS-based) lookups
- New `--hospitals-csv` and `--bkg-*` CLI flags for external geographic input
- 8th output artifact: `geo_lineage.md` documenting data sources and licenses
- Property-based tests for geographic plausibility (population correlation, AGS hierarchy invariants)

### Changed
- `metadata.json` now includes `geo_lineage` block when scenario uses geographic input

### Notes
- OSM data is treated as external snapshot input, not fetched at generation time
- BKG VG250 data is treated as external geometry input, not fetched at generation time
- Both data sources require attribution per their licenses (ODbL, dl-de/by-2-0)
```

---

## 13. Hand-off checklist before starting Phase 5 (Pharma implementation)

Before opening `prompts/05_pharma_implementation.md` in Claude Code:

- [ ] synth-datagen audit complete (`audit_report.md` exists)
- [ ] synth-datagen refactor complete (src layout, Pydantic, tests passing)
- [ ] SaaS scenario extension complete (PLG + Vertical sub-modes, both passing benchmark tests)
- [ ] Repo at v0.2.0 tag
- [ ] OSM snapshot of German hospitals fetched and committed to gis-territory-optimization repo
- [ ] BKG VG250 ZIP downloaded, both LAN and KRS GeoJSON committed to gis-territory-optimization repo
- [ ] `data/osm_hospitals_germany_<YYYYMMDD>.csv` validated: ≥3000 rows, no NULL coordinates, all in DE bounding box
- [ ] `data/de_bundeslaender_VG250.geojson` validated: 16 features, valid geometries
- [ ] `data/de_landkreise_VG250.geojson` validated: ~401 features, all parent AGS resolves to a Bundesland
- [ ] Read this integration notes document end-to-end
- [ ] Read `Coding_Agent_Prompt_synth_datagen_Pharma.md` end-to-end
- [ ] In a fresh Claude Code session: "Read prompts/05_pharma_implementation.md and execute it"

When all 11 boxes are checked, Phase 5 can begin.
