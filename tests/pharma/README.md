# Pharma test suite — quick reference

## Layout

- `tests/pharma/test_*.py` — fast-lane unit + smoke tests. Run on every
  pytest invocation; total budget per file <2 s wall time.
- `tests/property/test_pharma_invariants.py` — Hypothesis property tests
  (slow lane, auto-marked `slow` via `tests/property/conftest.py`).
- `tests/fixtures/pharma/` — hermetic mini-fixtures (3 BLs / 12 LKs /
  20 hospitals). See `tests/fixtures/pharma/README.md` for provenance.

## Running

```bash
# Fast lane only (default).
pytest tests/pharma/

# Slow lane (Hypothesis property suite).
pytest -m slow tests/property/test_pharma_invariants.py

# Full suite (fast + slow).
pytest -m 'slow or not slow' tests/
```

## `real_geo` marker

Tests that depend on **real-scale** German geography are marked
`@pytest.mark.real_geo` and **skipped by default**. They need the real
BKG VG250 GeoJSONs + an OSM hospital snapshot to be meaningful; the
hermetic fixtures (3 synthetic Bundesländer with AGS `01/09/11`) can't
reproduce statistical patterns that depend on the real 16-BL set.

Specifically:

- **BL-09 / BL-05 / BL-08 rep concentration (Pharmalotse REQ-4):**
  ~50 % of pharma reps are home-located in Bayern, NRW, and Baden-
  Württemberg. The fixture has only AGS `09` from that triplet, so
  the concentration test would always trivially pass with the BL-09
  weight applied. Real BL set is required.
- **Population correlation (REQ-1):** Spearman ρ > 0.7 between
  account density per Bundesland and DESTATIS population. Spearman
  on n=3 BLs has only six possible values; the test is statistically
  meaningless. Real 16-BL fixture required.
- **Top-20% Landkreis concentration at production scale:** the
  Pareto coefficient on n=12 Landkreise (fixture) saturates fast. A
  meaningful concentration test needs ~401 real Landkreise.

To enable these tests locally with real data:

```bash
# 1. Fetch real fixtures into a directory of your choice.
#    See prompts/pharma/04_integration_notes.md §4 for sources:
#    - OSM hospitals (Overpass API, ODbL).
#    - BKG VG250 Bundesländer + Landkreise (gdz.bkg.bund.de, dl-de/by-2-0).
#
# 2. Point the env var at that directory:
export PHARMA_REAL_GEO_DIR=/path/to/real_geo_fixtures

# 3. Run the real-geo subset.
pytest -m real_geo tests/property/test_pharma_invariants.py
```

The directory must contain three files at fixed names so tests can
locate them without further config:

- `osm_hospitals_germany.csv`
- `bundeslaender_VG250.geojson`
- `landkreise_VG250.geojson`

## When NOT to skip

- CI never runs `real_geo` (no env var set, no real fixtures
  committed). The marker is a developer-side opt-in; production
  validation happens at example time (commit 18's
  `examples/pharma_medicorp.py`) where the user supplies real
  fixtures explicitly.
- Adding new tests that depend on real geography MUST add the
  `@pytest.mark.real_geo` marker — otherwise CI will run them and
  fail trying to find files that aren't there.

## Stream isolation discipline

Pharma tests must not directly call `np.random.default_rng(...)` or
`numpy.random.default_rng(...)` in *production* code. The
`test_no_direct_default_rng_calls_in_pharma_package` test in
`tests/pharma/test_engine_smoke.py` walks the package AST and fails
if any direct call exists. Test code may use `default_rng` freely
because the AST scan only looks at `src/synth_datagen/pharma/`.
