# Phase 2 Refactor Log — feat/refactor-from-audit

Branch: `feat/refactor-from-audit`
Baseline: `v0.1.0-preaudit` (commit `d954b50`)
Backward-compat protocol: `python scripts/baseline_diff.py` capture/compare with
shrunken row overrides for retail/saas/fintech/logistics at seed=42, asserted
empty after every behavioural commit.

## Commits

### chore: add Phase 2 prompt and baseline-diff helper — `f366968`
- Files changed: `prompts/audit/phase2_refactor.md`, `scripts/baseline_diff.py`
- Purpose: capture the working scope and the verification harness used
  throughout Phase 2.

### refactor: drop dead SchemaType.NF3 / SchemaType.MIXED variants — `5435171` (P2-9)
- Files changed: `src/config.py`, `src/main.py`, `tests/test_regressions.py`
- Tests added: `test_schema_type_only_exposes_star`
- Backward compat: empty diff
- Removes the unreachable validator branch and the type-system foot-gun.

### fix: require explicit rng in distribute_counts — `7fd1f74` (P2-4)
- Files changed: `src/utils.py`, `tests/test_regressions.py`
- Tests added: `test_distribute_counts_requires_rng`
- Backward compat: empty diff (no live caller hit the silent fallback)
- Closes the `default_rng(42)` foot-gun that shadowed the user's seed.

### refactor: rename package to synth-datagen with src layout — `2f06c6d` (P0-2, P1-1)
- Files changed: 60+ (whole-repo move + import rewrites)
- Backward compat: empty diff after `pip install -e .`
- `src/*` → `src/synth_datagen/*` with `git mv` (history preserved).
- Package name `synthetic_data` → `synth-datagen`; version `3.0.0` → `0.2.0-dev`.
- Console scripts repointed at `synth_datagen.*`; root `conftest.py` deleted.
- README, quick_guide_README, run_demo, scripts, tests updated.

### refactor: extract RNG factory and migrate every default_rng call site — `f35bd21` (P0-3, P1-11)
- Files changed: `src/synth_datagen/rng.py` (new), `discounts.py`, `utils.py`,
  `kupferkanne_rfm.py`; `tests/test_rng_factory.py` (new)
- Tests added: 6 contract tests for the factory
- Backward compat: empty diff
- Single `make_rng(base_seed, concern)` factory + `SALT_REGISTRY`. Legacy
  `master` salt is 0, `discounts` keeps the `b"D15C0UNT"` mask. Future
  scenarios (Phase 5/6) MUST register a distinct salt before drawing.

### feat: unify CLI under one synth-datagen entry point — `32e157c` (P1-2)
- Files changed: `src/synth_datagen/cli.py` (new), `pyproject.toml`,
  `tests/test_unified_cli.py` (new)
- Tests added: 4 unified-CLI contract tests
- Backward compat: empty diff
- Single `synth-datagen` console script with sub-commands per scenario;
  the four legacy console scripts remain as transitional aliases.

### docs: add MIT LICENSE and declare it in pyproject — `48d59f6` (P0-1)
- Files changed: `LICENSE` (new), `pyproject.toml`, `tests/test_unified_cli.py`
- Tests added: `test_license_file_present_and_declared`
- Clears the public-release blocker.

### fix: clear the four real mypy bugs called out by the audit — `b071575` (P1-9)
- Files changed: `pipeline.py`, `monthly_sales.py`, `saas_v3/vocab.py`,
  `pyproject.toml`
- Backward compat: empty diff
- Annotates the scenario→generator mapping, drops the `monthly_sales`
  redefinitions, gives `appended_tables` and `vocab.counter` proper types.
- `mypy` and `types-PyYAML` are now declared dev deps.

## End-of-phase metrics

- Tests: 127 → **140 pass** (+13 new contract tests)
- Coverage: 91 % → **91 %** (held — Phase 3 will push to 85 %+ on the weak modules)
- Baseline diff retail/saas/fintech/logistics, seed=42: **empty** ✓ on every behavioural commit
- Conventional commits: **8 / 8**
