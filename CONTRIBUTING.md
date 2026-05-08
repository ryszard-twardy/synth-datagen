# Contributing to synth-datagen

Thanks for taking the time to contribute. This file is the canonical
reference for development setup, conventions, and how a change should
move from your fork to `main`.

## Development setup

Prerequisites: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ryszard-twardy/synth-datagen
cd synth-datagen
uv venv
source .venv/bin/activate                # PowerShell: .\.venv\Scripts\Activate.ps1
uv pip install -e ".[test,docs]"
pre-commit install
```

The `[test]` extra installs `pytest`, `pytest-cov`, `mypy`, `hypothesis`,
`ruff`, `bandit`, and `pre-commit`. The `[docs]` extra adds
`mkdocs-material`, `mkdocstrings[python]`, and `pymdown-extensions` for
local docs preview.

Quick smoke check that the dev install is wired up:

```bash
synth-datagen --help
synth-datagen scenarios
pytest --no-cov                          # fast lane, ~60 s
```

If `pytest` reports anything other than green, your environment is
fighting you — fix it before writing code.

## Running the test suite

```bash
pytest                                   # default fast lane (slow tests skipped)
pytest -m slow                           # slow lane only (Hypothesis + saas_v3)
pytest -m 'slow or not slow'             # full suite — what CI runs
pytest --cov                             # with coverage (80% gate enforced)
```

CI runs the full suite on Python 3.11, 3.12, and 3.13 across two pytest
lanes (`--cov-append` between them) and gates merges on
`coverage report --fail-under=80`.

## Documentation site

```bash
uv run mkdocs serve                      # http://127.0.0.1:8000
uv run mkdocs build --strict             # what CI / GitHub Pages run
```

`--strict` rejects any warning (broken links, missing nav entries, dead
auto-references). Always run it before opening a docs PR.

The site is published by `.github/workflows/docs.yml` on push to `main`,
so changes only appear at <https://ryszard-twardy.github.io/synth-datagen/>
once your PR merges. The docs `changelog.md` page inlines the root
`CHANGELOG.md` via a `pymdownx.snippets` directive — anything you put
under `## [Unreleased]` will show on the public site at next deploy, so
keep that section to released-style bullets, not free-form notes.

## Conventional Commits

Commit subjects follow [Conventional Commits 1.0](https://www.conventionalcommits.org/).
Use the type that best describes what the commit changes:

| Type | When |
|---|---|
| `feat` | New scenario, new exporter, new CLI flag |
| `fix` | Bug fix |
| `docs` | README / docs/ / CONTRIBUTING / SECURITY / CHANGELOG |
| `test` | Tests only |
| `refactor` | Behaviour-preserving structural change |
| `chore` | Tooling, deps, CI |
| `build` | Packaging (pyproject, build-system) |
| `ci` | GitHub Actions workflow changes |
| `perf` | Performance improvement with no behaviour change |

Examples from this repo's history:

```
feat(saas): allow per-feature rank-bucket overrides
fix(parquet): use is_object_dtype, not `is object`, for numpy O dtype
docs(readme): rewrite README for v0.2.0 publication
test: harden coverage on parquet/schema_builder/sql_exporter (P7)
build(pypi): expand pyproject metadata and add [docs] extra
```

**No `Co-authored-by:` trailers.** This repo is single-author by
convention; trailers added by automation will be rejected at review.

## Pull-request checklist

Before requesting review, confirm:

- [ ] Branch is rebased on `main` (no merge commits in your range).
- [ ] `pytest -m 'slow or not slow'` passes locally.
- [ ] `pre-commit run --all-files` is clean (ruff, ruff-format, bandit,
      whitespace, EOF, line endings).
- [ ] If you touched `docs/` or any docstring referenced by
      `mkdocstrings`, `uv run mkdocs build --strict` passes.
- [ ] If you added a public function or behaviour, `CHANGELOG.md`
      `[Unreleased]` has an entry under the appropriate heading
      (`Added` / `Changed` / `Fixed`).
- [ ] If you changed any CLI flag, the README scenarios table and
      `docs/quickstart.md` are updated.
- [ ] PR description explains *why*, not just *what* — link the issue
      or design discussion.

## How to add a new scenario

1. **Define the schema.** Add a new value to `Scenario` in
   `src/synth_datagen/config.py`. Keep the enum value lowercase
   (`"healthcare"`, not `"Healthcare"`).
2. **Implement the generator.** Create
   `src/synth_datagen/generators/<name>.py` with a class subclassing
   `BaseGenerator`. Implement `get_raw_schema()` (returns
   `(tables, relations)`) and `generate_table(table, graph, fk_pools)`
   (yields `pd.DataFrame` chunks). Look at
   [`generators/saas.py`](src/synth_datagen/generators/saas.py) for the
   simplest reference.

   If your generator depends on heavy or platform-specific libraries
   (geopandas, shapely, image libraries, ML frameworks), gate them
   behind a `[<scenario>]` optional extra in `pyproject.toml` and
   guard the imports lazily so a base install never pays the cost.
   See the `[pharma]` extra (geopandas + shapely) in `pyproject.toml`
   and the lazy import + friendly error pattern in
   [`src/synth_datagen/pharma/cli.py`](src/synth_datagen/pharma/cli.py).
3. **Wire it into the registry.** Add the import + dispatch entry to
   `src/synth_datagen/pipeline.py::_get_generator`.
4. **Cross-scenario utilities (if any).** If your scenario adds
   primitives reusable across scenarios — spatial joins, hierarchy
   walkers, coordinate-system helpers, period-windowing math — put
   them in a top-level shared module like
   [`src/synth_datagen/geo.py`](src/synth_datagen/geo.py) rather than
   scenario-local code. This prevents duplication when future
   scenarios need the same primitive and keeps the per-scenario
   module focused on business logic.
5. **Tests.**
   - `tests/test_<name>_realism.py` — invariants (FK integrity, totals
     reconcile, no NaNs in PK columns).
   - `tests/test_property_<name>.py` — Hypothesis property tests
     covering every seed-stable invariant. Add the `@pytest.mark.slow`
     marker.
   - `tests/test_unified_cli.py` — add the new sub-command to the
     parametrised list.
   - **Fixtures.** If your scenario reads external data (CSVs,
     GeoJSON, etc.), commit hermetic mini-fixtures under
     `tests/fixtures/<name>/` with a `README.md` documenting
     provenance: license, source URL or "hand-authored synthetic",
     generation seed if applicable. See
     [`tests/fixtures/pharma/README.md`](tests/fixtures/pharma/README.md)
     for the canonical example. Tests that need real production-scale
     data gate behind a dedicated marker (e.g. `@pytest.mark.real_geo`,
     registered in `pyproject.toml`'s `[tool.pytest.ini_options]
     markers`) and are skipped by default — opt in via env var or
     `pytest -m`.
6. **Docs.** Add `docs/scenarios/<name>.md` with sample output, table
   inventory, and full config reference. Link it from
   `docs/scenarios/index.md` and from the README scenarios table.
7. **Changelog.** Add a `Added` bullet under `[Unreleased]`.
8. **Verify.** Run the full suite and `mkdocs build --strict`. Open the
   PR with example output (a `tree out/<name>/` listing) in the body.

## Documenting gotchas

When you hit a non-obvious build, CI, or test trap likely to be
repeated by future contributors, drop a `memory/<slug>.md` note. The
[`memory/`](memory/) folder is the project's curated list of
scenario-agnostic technical lessons.

Format: **Title / Symptom / Root cause / Fix / References**. See
existing entries for canonical examples:

- [`memory/ruff-pin-coupling.md`](memory/ruff-pin-coupling.md)
- [`memory/cli-tests-ansi-on-ci.md`](memory/cli-tests-ansi-on-ci.md)
- [`memory/version-coupling.md`](memory/version-coupling.md)
- [`memory/cross-platform-python-path.md`](memory/cross-platform-python-path.md)

Update [`memory/README.md`](memory/README.md)'s index table with a
one-line summary in the same commit. Keep entries short, focused on
the *one* lesson, and free of personal/workflow context — they're
project-level reference, not session notes.

## Reporting issues

Bugs, missing scenarios, or unclear documentation: open an issue at
<https://github.com/ryszard-twardy/synth-datagen/issues> with a minimal
reproduction (the `--seed` you used and the exact CLI command). For
suspected security issues, see [SECURITY.md](SECURITY.md) instead.

## Code of conduct

Be respectful and assume good faith. Disagreements about technical
trade-offs are expected — make your case with evidence and move on.
