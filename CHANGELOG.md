# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- _nothing yet_

### Changed

- _nothing yet_

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
