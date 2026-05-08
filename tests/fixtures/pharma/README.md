# Pharma scenario hermetic test fixtures

Hand-authored synthetic data used by the pharma test suite. **Not derived
from BKG VG250, OSM, or any public source.** All geometries are simple
axis-aligned rectangles with round-number coordinates that do not
correspond to any real Bundesland or Landkreis boundary; AGS values are
illustrative only.

## Why hermetic

The Phase-3 lesson on flaky tests applies here: tests that depend on
external data downloads, geopandas-bundled datasets, or large fixtures
become slow and flake on CI. These fixtures are <100 KB total and cover
the structural cases the engine and `geo.py` must handle without giving
the engine real-world calibration data — that comes from caller-side
BKG/OSM snapshots in production.

Real pharma generation requires the caller to supply:

- **OSM hospital snapshot CSV** — license: ODbL.
- **BKG VG250 Bundesländer GeoJSON** — license: dl-de/by-2-0.
- **BKG VG250 Landkreise GeoJSON** — license: dl-de/by-2-0.

`synth-datagen` does **not** bundle any of these. The fixtures here are
the project's own MIT-licensed synthetic stand-ins.

## Layout

| File | Purpose | Rows / features |
|------|---------|-----------------|
| `bundeslaender_test.geojson` | 3 Bundesländer (rectangles) | 3 |
| `landkreise_test.geojson` | 12 Landkreise tiling those rectangles | 12 |
| `osm_hospitals_DE_test.csv` | 20 synthetic hospitals + clinics | 20 |

### Bundesländer geometry

Three rectangles in WGS84 (EPSG:4326) covering an artificial bounding
box of lat 50–53, lon 10–14. The AGS values (`01`, `09`, `11`) are
chosen to overlap with the real-world AGS namespace so engine code that
filters or joins on AGS is exercised, but the geometries are entirely
synthetic.

| AGS | Synthetic name | Lat range | Lon range | Synthetic population |
|-----|----------------|-----------|-----------|----------------------|
| `01` | "Bundesland Alpha" | 52–53 | 10–12 | 2,500,000 |
| `09` | "Bundesland Beta" | 50–52 | 10–12 | 12,000,000 |
| `11` | "Bundesland Gamma" | 50–53 | 12–14 | 4,000,000 |

### Landkreise geometry

12 axis-aligned rectangles, 4 per Bundesland, tiling the parent BL
exactly with no overlap and no gap. Parent AGS (first 2 digits of
landkreis AGS) matches the BL AGS.

### OSM hospitals CSV

20 rows. Columns match the schema documented in
`prompts/pharma/04_integration_notes.md` §4. Mix of `amenity=hospital`
(with `beds≥50`, used by acute-care sub-mode) and `amenity=clinic`
(used by specialty-care sub-mode). All coordinates fall strictly
*inside* one of the 12 Landkreis polygons (no border placement) so
spatial join is unambiguous. Hospital names are invented German-style
(e.g. "Klinikum Alpha-Stadt"), not copied from any real institution.

## Coordinate system

All GeoJSON files are EPSG:4326 (WGS84 lon/lat). The `geo.py`
production code reprojects real BKG VG250 (EPSG:25832) into EPSG:4326
on load; the test fixtures skip that step by being authored in 4326
directly. A test in `tests/pharma/test_geo.py` confirms reprojection
works on a synthetic 25832 fixture too (TBD — added when geo.py lands).

## Provenance contract

Every commit that touches files in this directory MUST preserve:

1. Round-number coordinates only (decimal multiples of 0.25 or simpler).
2. Invented institution names — no real hospital, clinic, or specialist
   group.
3. PLZ values restricted to the `99001`–`99099` range (Germany has
   never assigned that range, so even an accidental match is a
   non-collision).
4. AGS values consistent with the parent table above. New Bundesländer
   added only with hand-picked unused 2-digit codes.
5. License: project MIT — these fixtures are owned by synth-datagen.
