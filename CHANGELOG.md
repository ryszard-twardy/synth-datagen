# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Phase 6 in progress — Pharma scenario.** Acute-care + specialty-care
  sub-modes targeting the German pharmaceutical market. Calibrated
  against DESTATIS Krankenhausstatistik, PHAGRO wholesale data, IQVIA
  DKM, vfa innovation data, and Pharmalotse field-force benchmarks. New
  shared `geo.py` module for AGS-based hierarchical lookups
  (Bundesländer + Landkreise). New optional extra `[pharma]` pulling in
  `geopandas` + `shapely`. Full release notes accumulated as commits
  land on `feat/pharma-scenario`; this stub will be expanded into the
  `[0.3.0]` block at release time.

### Changed

- _nothing yet_

### Fixed

- _nothing yet_

### Deferred to v0.3.x

- **Pharma REQ-2 (ownership distribution validation)** and **REQ-6
  (product catalog spread validation)** are not part of v0.3.0's
  benchmark-validation pass. Both checks need production-scale
  data (real BKG VG250 + OSM snapshot, account_count ≥ 2000) to
  produce meaningful pass/fail signals; running them on the
  hermetic test fixtures or smoke-scale outputs would always
  resolve to `skip`. The five v0.3.0 checks (REQ-1 AGS hierarchy +
  population correlation, REQ-3 revenue median band, REQ-4 visit
  frequency band, REQ-5 top-20 % revenue concentration, REQ-7
  orders FK integrity) are sufficient to gate the engine's
  bit-stable contract; REQ-2 / REQ-6 calibration lands when the
  v0.3.x release brings real-fixture support upstream of the
  validation pass.
- **University-hospital revenue boost (REQ-3 calibration).**
  v0.3.0 draws Universitätsklinikum revenue from the same
  log-normal as other acute accounts. The spec REQ targets 8-12 %
  revenue concentration on the ~3 % university accounts; v0.3.0
  uses a loose validation envelope (0.1-25 %) and defers the
  multiplier-based calibration to v0.3.x.
- **Real-data BL population correlation lookup.** REQ-1's
  Spearman ρ check against DESTATIS population is wired through
  `validate.py` but skipped pending the engine surfacing per-BL
  populations through `geographic_metadata`. Round-trip lands in
  v0.3.x.

## [0.2.1] — 2026-05-07

### Added

- **`saas-v3` `plg-usage-based` sub-mode (Phase 5).**
  - New `run.mode` field in saas_v3 YAML config; defaults to `legacy`
    so every existing config remains byte-stable. Set
    `run.mode: plg-usage-based` to opt in.
  - 8th table `subscription_events` with the full 5-movement MRR
    waterfall: `new`, `expansion`, `contraction`, `churn`, and
    `reactivation`. `SUM(mrr_delta) GROUP BY account_id` matches the
    account's current MRR within ±0.01 EUR — verified by a Hypothesis
    property test across 8 random seeds per run.
  - `--benchmark-validation` CLI flag on `synth-datagen saas-v3 generate`
    (saas-v3 only). Computes NRR, GRR, lifetime-churn-rate, and a
    forward-compat `trial_conversion_rate` stub against KeyBanc 2024 +
    Benchmarkit 2025 target ranges; writes `benchmark_validation.md` to
    the run root and exits non-zero on failure.
  - `BenchmarkConfig` model (`benchmarks:` block) with calibrated
    defaults — override per-config without code changes.
  - `configs/saas_v3.plg.yaml` reference config exercising the new mode.
  - Hypothesis property test
    `tests/property/test_saas_v3_invariants.py` for the MRR-delta
    sum invariant.
  - `subscription_event_id` ID format (`sevt_NNNNNNNNNN`) registered in
    `IdFactory`.

### Changed

- **saas_v3 RNG migrated to the central `make_rng` factory** under the
  newly registered `"saas_v3"` salt (`0x5AA50000`). `SaaSV3Engine._rng`
  and `DefectInjector._rng` no longer call `np.random.default_rng`
  directly — every saas_v3 random draw now flows through
  `make_rng(seed, "saas_v3").spawn(N)`. saas_v3 byte output shifted
  once at this release; pinned going forward by
  `scripts/baseline_diff.py`.
- `scripts/baseline_diff.py` now captures `saas_v3` alongside the four
  legacy scenarios. Pre-v0.2.1 baselines without a `saas_v3/`
  subdirectory are gracefully skipped (not flagged as missing).

### Fixed

- _nothing yet_

## [0.2.0] — 2026-05-07

First public release. Refactored, tested, documented, and ready for PyPI.

### Added

- **Phase 4 — Documentation & publication prep.**
  - Rewritten `README.md` (159 lines) with dual quickstart (source today /
    PyPI from v0.2.0), Mermaid architecture diagram, real CLI flag
    reference, and a citation block.
  - MkDocs Material site under `docs/` covering quickstart, every
    scenario, architecture deep dives (RNG isolation, distributions,
    quality injection), loading recipes (Power BI, BigQuery, Postgres),
    auto-generated API reference via `mkdocstrings`, and the changelog.
  - `examples/` directory with three runnable, verified scripts:
    `quickstart_retail.py` (~6 s), `quickstart_saas.py` (~2 s,
    `data-quality=medium`), and `kupferkanne_full.py` (~5 min, full
    39-month period).
  - `CONTRIBUTING.md` with `uv`-based dev setup, conventional-commit
    guide, PR checklist, and a "how to add a new scenario" walkthrough.
  - `SECURITY.md` documenting supported versions and the vulnerability
    reporting flow.
  - `.github/workflows/docs.yml` — GitHub Pages deploy on push to `main`.
  - `pyproject.toml` metadata complete for PyPI: full classifiers
    (`Development Status :: 4 - Beta`, `Operating System :: OS
    Independent`, `Topic :: Software Development :: Testing`, `Typing ::
    Typed`, all three Python versions), expanded keywords, project URLs
    (Homepage, Documentation, Repository, Issues, Changelog), and a new
    `[docs]` extra (`mkdocs-material`, `mkdocstrings[python]`,
    `pymdown-extensions`).

### Changed

- `run_demo.py` (a 4-scenario smoke test that didn't really document
  anything) was renamed to `examples/quickstart_retail.py` and slimmed to
  a focused single-scenario quickstart. Tests follow the rename.
- README description updated to lead with the three differentiators
  (referential integrity, deterministic seeding, configurable quality
  injection) rather than a generic "synthetic dataset generator".

### Fixed

- **Parquet exporter dropped the object-column sanitiser branch.**
  `_sanitise_chunk` in `src/synth_datagen/exporters/parquet_exporter.py`
  used `if dtype is object:` to detect numpy object-dtype columns, but
  `numpy.dtype('O') is object` is `False` in Python — identity vs
  equality. The result: every datetime/date/None object column silently
  bypassed sanitisation and round-tripped to Parquet with `object` dtype
  instead of `datetime64`. Fixed by switching to
  `pd.api.types.is_object_dtype(dtype)`. CSV exports were unaffected
  (`scripts/baseline_diff.py` confirmed byte-identical CSVs across
  retail / saas / fintech / logistics). Caught by the new direct unit
  tests added in P7.
- **fintech leap-day card expiry crash** — moved card `valid_to` 1 March
  forward when a 4-year offset lands on Feb 29 in a non-leap year.
- **saas feature-rank empty bucket fallback** — when a user-defined rank
  bucket excluded every feature, the engine raised; it now falls back to
  the full feature list.

### Phase 3 — test hardening (P1–P9)

- Hypothesis property tests covering invariants for every scenario
  (retail, saas, fintech, logistics, `kupferkanne_rfm`; P3 / P2-6).
- Determinism and CSV byte-equality tests for fintech and logistics
  (P2-7, P2-8).
- Direct unit tests for `parquet_exporter`, `schema_builder`,
  `sql_exporter` extras, and `saas_v3.cli`. Per-module coverage:
  parquet 27 → 98 %, schema_builder 100 %, saas_v3.cli 19 → 99 %.
  Combined `src/synth_datagen/` coverage with the slow lane: **94 %**.
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) with a
  Python 3.11 / 3.12 / 3.13 matrix running ruff lint + format-check,
  mypy (advisory), bandit `-ll`, two-lane pytest (fast + slow with
  `--cov-append`), an `if: always()` `coverage report --fail-under=80`
  gate, and Codecov upload from the 3.12 leg.
- `.pre-commit-config.yaml` mirroring the CI toolchain (ruff,
  ruff-format, mypy on `manual` stage, bandit, whitespace / EOF /
  line-ending hooks). `pre-commit>=3.5.0` added to the `[test]` extra.
- Default `pytest` invocation now skips `@pytest.mark.slow` tests so the
  inner-loop completes in <60 s. Run the full suite with
  `pytest -m 'slow or not slow'` (CI does this in two appended lanes).
- Coverage thresholds moved from CLI flags to `[tool.coverage.report]`
  in `pyproject.toml` so CI, pre-commit, and local `coverage report`
  see the same gate (80 % combined floor).

### Deviations from `prompts/audit/phase3_tests.md`

Three intentional deviations from the literal Phase-3 spec:

1. **CI runs pytest in two lanes (fast + slow with `--cov-append`)**
   instead of a single `pytest --cov-fail-under=80` invocation. The
   fast lane keeps developer feedback under a minute on push; the slow
   lane exercises the saas_v3 pipeline and the Hypothesis property
   suite. The combined coverage gate is the same.
2. **`mypy src/` runs `continue-on-error: true`** (advisory) until the
   57 pre-existing typing errors elsewhere in the codebase are paid
   down. Pre-commit mirrors this by gating the mypy hook behind
   `stages: [manual]`. Flip both when the typing debt is cleared.
3. **Bandit added at `-ll` (medium-severity-or-higher).** The spec
   mentions bandit in prose but not in the YAML; CI runs it with
   `pass_filenames: false` so the invocation matches the local
   pre-commit hook. The lone Low/Medium SQL-injection finding in the
   SQL exporter is annotated `# nosec B608` with justification (values
   pass through `_sql_val` quoting; table/column names come from a
   closed config schema).

## [0.1.0-preaudit] — 2026-04-30

Pre-audit baseline. Internal-only; not on PyPI. Initial multi-scenario
generator (retail, saas, fintech, logistics, kupferkanne-rfm,
monthly-sales, saas-v3) with the now-removed parallel console scripts.
