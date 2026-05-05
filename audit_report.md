# synth-datagen Audit Report

- **Date:** 2026-05-05
- **Auditor:** Claude Code (Phase 1 audit, Opus 4.7)
- **Repo state (HEAD):** `eedaa1d4c9b976782aaec22b05024f107960746a` (`main`, tag `v0.1.0-preaudit` at parent commit `d954b50`)
- **Working dir:** `X:\Python\projects\synth-datagen`
- **Methodology:** Read-only; tools installed in throwaway venv at `C:\Temp\synth-audit-venv` (not project `.venv`).

---

## Executive Summary

- **Overall code health score:** **6.5 / 10**
  Solid statistical core, fully reproducible classic scenarios, 91% test coverage, zero ruff lint warnings. But: package metadata mismatched with planned public name, no LICENSE, structural RNG-isolation pattern is fragile (only `discounts` is salted), four parallel CLI entry points instead of one, and no CI/CHANGELOG/CONTRIBUTING. The codebase is *almost* ready to publish — the gap is hygiene + structure, not correctness.

- **Findings:** **P0 = 3**, **P1 = 12**, **P2 = 14**, **P3 = 9** (total 38)

- **LOC:** 12,187 Python (38 source files in `src/`, 26 test files in `tests/`, 1 in `scripts/`)

- **Test coverage:** **91 %** overall (target ≥85% already exceeded). 127 tests pass. Runtime **5m 52s** (target <60s — see P1-12).

- **Reproducibility (Step 7, seed=42, classic scenarios):**
  - retail   → empty diff ✓
  - saas     → empty diff ✓
  - fintech  → empty diff ✓
  - logistics→ empty diff ✓
  *Single-run-vs-rerun reproducibility holds.* The fragility is in the **insertion-order-vs-future-changes** dimension (see P0-3).

- **Critical recommendations (top 3):**
  1. **Block public release until name + LICENSE + version are aligned with the master plan** (`synth-datagen` v0.2.0 + MIT/Apache LICENSE). Today the wheel would publish as `synthetic_data` v3.0.0 with no license — wrong on both counts.
  2. **Refactor RNG isolation to a single factory with per-concern salts before any new scenario lands** (SaaS sub-modes, Pharma). Currently every generator consumes from one shared `self.rng`; any new field added to retail will shift the whole stream and break the baseline-diff guarantee.
  3. **Collapse the four CLIs (`synthetic-data` / `synthetic-monthly-sales` / `synthetic-saas` / `synthetic-rfm-kupferkanne`) into one `synth-datagen` Typer app** with sub-commands per scenario, before SaaS sub-modes are added. Otherwise the surface area keeps multiplying.

---

## Findings by Severity

> Notation: each finding has an ID (`P0-N` / `P1-N` / etc.), a one-line title, file/line refs, evidence, and a suggested fix.
> P-numbers are stable IDs you can reference in Phase 2 commit messages (`fix: P0-2 align package name with synth-datagen`).

### P0 — Critical (block release)

#### P0-1  No LICENSE file in the repo
- **Evidence:** `ls LICENSE*` → no match. Master plan §10 lists `LICENSE` as DoD; pyproject.toml has no `license` field.
- **Why P0:** Without an explicit license the default is "all rights reserved" — nobody can legally fork, install, or use this.
- **Fix:** Add `LICENSE` (MIT recommended for portfolio use) and set `[project] license = {text = "MIT"}` in `pyproject.toml`.

#### P0-2  Package identity mismatch (`synthetic_data` v3.0.0 vs `synth-datagen` v0.2.0)
- **Evidence:**
  - `pyproject.toml:6-7` → `name = "synthetic_data"`, `version = "3.0.0"`
  - Repo dir: `X:\Python\projects\synth-datagen`
  - Master plan §1, §3: target name `synth-datagen`, target tag `v0.2.0`
  - `README.md:2` → `# synthetic-data` (third spelling)
  - Console scripts: `synthetic-data`, `synthetic-monthly-sales`, `synthetic-saas`, `synthetic-rfm-kupferkanne` (none use `synth-datagen`)
- **Why P0:** PyPI registers names globally. Publishing today would (a) take the wrong name, (b) collide with anything already at `synthetic_data`, (c) break the portfolio-narrative "I built `synth-datagen`."
- **Fix:** Single rename pass: `name = "synth-datagen"`, package import `synth_datagen`, version `0.2.0` (Phase 4 will tag this), unify console scripts under one `synth-datagen` entry point (cf. P1-2).

#### P0-3  Single shared `self.rng` consumes for all generation concerns → backward-compat break risk on any future addition
- **Evidence:**
  - `src/utils.py:22-27` `seed_everything(seed)` returns one `np.random.default_rng(seed)`.
  - `src/pipeline.py:59-60` passes that single `rng` to every generator.
  - Only `src/discounts.py:14,23` uses an XOR salt (`b"D15C0UNT"`); every other concern in `retail_builder.py`, `saas.py`, `fintech.py`, `logistics.py` reads from the master stream sequentially.
  - Master plan §"Rule 4" + Phase 2 prompt §"RNG stream isolation (HARD requirement)": *"Adding new logic doesn't shift existing RNG streams (bit-for-bit compatibility)."*
- **Why P0:** The whole point of Phases 5/6 (SaaS sub-modes, Pharma) is to extend without breaking retail/saas/fintech/logistics seed=42 diffs. With today's design, inserting one `self.rng.choice(...)` anywhere in a generator's `__init__` shifts every subsequent draw, and the baseline-diff in Phase 2 will fail on the very first commit. Reproducibility-on-rerun (verified empty in Step 7) does **not** imply forward-compat-of-extension.
- **Note:** The promised pattern (`new_concern_rng = base_rng ^ 0xNEWCONCERN`) only exists for `discounts`. `saas_v3` does isolate per-concern via `_seed_from_label()` (good), but `kupferkanne_rfm.py:749,990` has two unrelated `np.random.default_rng(seed)` instantiations — also fragile.
- **Fix:** Phase 2 must extract a single `src/synth_datagen/rng.py` factory exposing `make_rng(base_seed, concern: str)` (or `int_salt`) and migrate every existing draw call. Document the registered salts as a table. Then run baseline-diff on every conversion commit.

---

### P1 — High (must fix before public release)

#### P1-1  No `src/<package>/` layout — package is the literal `src/` directory
- **Evidence:**
  - `pyproject.toml:43-45` `where = ["."], include = ["src*"]`; console script `synthetic-data = "src.main:app"`
  - `conftest.py:5` does `sys.path.insert(0, str(Path(__file__).parent))` to make this importable in tests.
  - `src/__init__.py` is empty (no `__version__`, no `__all__`).
  - Imports in tests are `from src.config import ...` (test-only namespace, not what users would import).
- **Why P1:** Publishable Python packages use the **src layout**: `src/synth_datagen/__init__.py` and `import synth_datagen`. The current layout makes `import src` the public API, which is hostile to consumers and breaks the moment two such packages live in one site-packages.
- **Fix:** Phase 2: rename `src/` → `src/synth_datagen/`, drop the root `conftest.py` sys.path hack, update all imports, add `__version__ = "0.2.0"` and `__all__` to `src/synth_datagen/__init__.py`.

#### P1-2  Four parallel console scripts instead of one CLI
- **Evidence:** `pyproject.toml:37-41` declares `synthetic-data`, `synthetic-monthly-sales`, `synthetic-saas`, `synthetic-rfm-kupferkanne`.
- **Why P1:** Master plan + SaaS extension prompt assume one CLI with sub-commands per scenario (`synth-datagen retail …`, `synth-datagen saas --sub-mode plg-usage-based …`, `synth-datagen pharma --sub-mode acute-care …`). Four binaries fragments the UX, doubles documentation surface, and makes the `--sub-mode` SaaS extension awkward.
- **Fix:** Phase 2: keep one `synth-datagen` Typer app, expose `retail|saas|fintech|logistics|monthly-sales|kupferkanne-rfm` as sub-commands. Keep the current entry-point names as transitional aliases (deprecation note in CHANGELOG).

#### P1-3  No CHANGELOG.md, CONTRIBUTING.md, SECURITY.md
- **Evidence:** `ls CHANGELOG* CONTRIBUTING* SECURITY*` → no match.
- **Why P1:** Master plan §10 DoD requires all three. Keep-a-Changelog is the table of contents for the v0.2.0 release; CONTRIBUTING/SECURITY are baseline OSS hygiene.
- **Fix:** Phase 4 deliverables (already in master plan).

#### P1-4  No CI workflow
- **Evidence:** `ls .github/workflows/` → directory does not exist.
- **Why P1:** Master plan §10: *"CI passes on Python 3.11/3.12/3.13."* Without CI there's no way to keep the repo green after the public release.
- **Fix:** Phase 3 deliverable (already in master plan §6).

#### P1-5  No pre-commit configuration
- **Evidence:** `ls .pre-commit-config.yaml` → no match.
- **Why P1:** Phase 2 prompt §"Code quality gates" expects pre-commit hooks for ruff/mypy/bandit. Without it, format drift returns the day after Phase 2 ends.
- **Fix:** Add `.pre-commit-config.yaml` in Phase 2 (ruff lint+format, mypy, bandit).

#### P1-6  pyproject metadata anonymized / under-specified
- **Evidence:**
  - `pyproject.toml:9` `authors = [{ name = "Data Engineer" }]` (placeholder)
  - No `[project.urls]` (Homepage / Issues / Changelog / Documentation)
  - No `license` field
  - Description is generic; keywords are minimal
- **Why P1:** PyPI listing will be unattributed and unlinked. Recruiter searching `pip show synth-datagen` sees no author and no project URL.
- **Fix:** Phase 4: full PEP 621 metadata (real name + email, `[project.urls]`, license, classifiers, refined description). Master plan already has the template.

#### P1-7  AGENTS.md is generic Codex/ECC content unrelated to this project
- **Evidence:** `AGENTS.md:1-97` is "ECC for Codex CLI" with mentions of `frontend-patterns`, `x-api`, `fal-ai-media`, `dmux-workflows`, etc. — none of which apply to synth-datagen.
- **Why P1:** Once the repo is public this is a confusing artifact. It also leaks "this was bootstrapped from a template" — fine, but only if intentional. Currently it's just noise.
- **Fix:** Phase 4: either delete or replace with a tight project-specific AGENTS.md (instructions for human + agent contributors). Suggest delete; CONTRIBUTING.md covers the same ground better.

#### P1-8  MEMORY.md is an internal scratchpad committed to git
- **Evidence:** `MEMORY.md:1-218` is a self-narrative covering "Recent Changes", "Guardrails For Future Changes", `LineNumber` rollout details. Looks like an auto-memory artifact from a previous session.
- **Why P1:** Internal artifact; ships to public repo. Either the auto-memory directory should be `.gitignore`d (it already is — `.claude/` line 63), or this file should be moved under `.claude/` and removed from git tracking.
- **Fix:** Phase 4: remove from git tracking (`git rm --cached MEMORY.md`) and add `MEMORY.md` to `.gitignore`, OR fold whatever is genuinely useful into CONTRIBUTING.md.

#### P1-9  `mypy --ignore-missing-imports` reports 19 errors in 10 files
- **Evidence:** Tool run from temp venv. Examples:
  - `src/pipeline.py:45` `Cannot instantiate abstract class "BaseScenarioGenerator"` (`mapping[scenario](...)` confuses the resolver — likely fixable with a `Protocol` or `Type[BaseScenarioGenerator]`)
  - `src/utils.py:256` `Incompatible types: list[int] vs list[str]` in `inject_duplicates` PK rebuild — real-looking type bug for non-identifier PK columns
  - `src/monthly_sales.py:394-395` `Name "order_ids" already defined on line 385`
  - `src/generators/retail_builder.py:624,626,761` `float(object)` arg-type
  - 4× missing yaml stubs (`types-PyYAML`)
  - 2× `Need type annotation` (`vocab.py:67`, `monthly_sales.py:475`)
- **Why P1:** Master plan §6 DoD: *"mypy: 0 errors on `--strict`."* Today even `--no-strict-optional` finds 19. The redefined-name issue and the int-vs-str list assignment are real correctness smells.
- **Fix:** Phase 2 (per finding) + Phase 3 strictness pass. Add `types-PyYAML` to dev deps.

#### P1-10  60 of 68 Python files would be reformatted by ruff
- **Evidence:** `ruff format --check src tests scripts` → "60 files would be reformatted, 8 files already formatted."
- **Why P1:** Ruff lint is clean (0 warnings). Format drift is mechanical, but until pre-commit lands, every commit will keep churning.
- **Fix:** One `ruff format .` commit at the start of Phase 2 (zero behavior change), then enforce via pre-commit.

#### P1-11  `kupferkanne_rfm.py` instantiates two un-salted master RNGs
- **Evidence:** `src/kupferkanne_rfm.py:749` `np.random.default_rng(seed)` and `:990` `np.random.default_rng(seed)` — both seeded with the same base, neither salted.
- **Why P1:** If the order of these instantiations is reordered (or one is added between them), reproducibility collapses silently. Two RNGs sharing one seed is also strictly equivalent to one — confusing intent.
- **Fix:** Migrate to the new `make_rng(base_seed, concern=…)` factory with explicit salts (`KUPFER_CUSTOMERS`, `KUPFER_ORDERS`, etc.) as part of P0-3.

#### P1-12  Test runtime ~6 minutes, dominated by two slow tests
- **Evidence:** `pytest --durations=10`:
  - `test_kupferkanne_v3_generation_writes_star_schema_outputs` setup: **215.18 s** (3m 35s)
  - `test_retail_dim_date_respects_row_override` call: **81.38 s** (1m 21s)
  - Together ≈ 50 % of total runtime.
- **Why P1:** Master plan §"Phase 3 success criteria": *"A single pytest invocation runs everything in < 60 seconds."* Today it's 6 minutes, so the CI loop will hurt and contributors will skip running tests locally.
- **Fix:** Phase 3: shrink the kupferkanne fixture (smaller row counts; the test is checking schema, not statistical fidelity), parametrize the dim_date test instead of generating a 1461-row date dimension fully, mark the heavy ones `@pytest.mark.slow` and exclude from default `pytest`.

---

### P2 — Medium (post-release improvements)

#### P2-1  Magic-number business benchmarks across all generators (50+ unsourced)
- **Evidence (sample):**
  - `retail_builder.py:418` `self.rng.beta(2.4, 2.4)` (margin) — no comment
  - `retail_builder.py:582-590` qty distribution `[0.44, 0.27, 0.16, 0.08, 0.05]` — no source
  - `fintech.py:219` `rng.normal(690, 85)` (FICO score) — no source
  - `saas.py:204` `bounded_lognormal(3.8, 1.1, 5, 5_000)` (employees) — no source
  - `saas_v3/config.py:133-137` churn 0.16, expansion 0.34, contraction 0.12, incident 0.08, seasonal 0.12 — no citations
  - Full list in subagent reports (architecture review).
- **Why P2:** Phase 1 prompt §"Distribution correctness" wants Beta/log-normal/Pareto parameters cited. Today a reviewer cannot tell whether 0.16 monthly churn is a SaaS benchmark or a guess.
- **Fix:** Phase 2/3: extract to `src/synth_datagen/benchmarks/<scenario>.py` with named constants and source comments (Recurly 2023, KeyBanc 2024, FICO public bands, etc.). Master plan SaaS prompt already calls for this pattern.

#### P2-2  Long methods with high cyclomatic complexity
- **Evidence (radon `cc -a -nb`):**
  - `retail_builder._build_orders_and_related` 187 lines, complexity rank **D** (CC ≈ 21+)
  - `saas_v3/engine._build_account_month_state` complexity rank **D**
  - `saas_v3/config.SaaSV3Config.validate_lists` complexity rank **D**
  - `saas_v3/validate._validate_clean_integrity` complexity rank **D**
  - `logistics._build_shipments_and_items` 77 lines, **C**
  - Average complexity overall **C (10.92)** — not a disaster, but the top tier is fat.
- **Fix:** Phase 2: split each `D` function into 3-4 helpers. TDD-ed extraction.

#### P2-3  No shared distribution / RNG factory module
- **Evidence:** `bounded_lognormal`, `weighted_choice`, `date_range_samples` exist in `src/utils.py` but each generator still calls `self.rng.beta`/`.normal`/`.lognormal` directly with hardcoded params (no source).
- **Fix:** `src/synth_datagen/distributions.py` with citation comments per parameter, used everywhere.

#### P2-4  `distribute_counts` silently falls back to `default_rng(42)`
- **Evidence:** `src/utils.py:112-113` `if rng is None: rng = np.random.default_rng(42)`.
- **Why P2:** Reproducibility hazard: any caller that forgets to pass `rng` gets a constant 42 stream regardless of the requested seed. Currently no caller hits this path (every call site passes `rng`), but the fallback is a foot-gun.
- **Fix:** Make `rng` required; raise on `None`. Add a unit test.

#### P2-5  Duplicated helpers between subsystems
- **Evidence:**
  - `_seed_from_label` defined in both `saas_v3/engine.py:73-75` and `saas_v3/defects.py:18-20`
  - `_allocate_counts` defined in both `saas_v3/engine.py:85-100` and `kupferkanne_rfm.py:127-141`
  - Local `COUNTRY_LOCALES`, `COUNTRY_REGIONS` in `kupferkanne_rfm.py` overlap with `COUNTRIES_WEIGHTED` in `utils.py:359-376`.
- **Fix:** Single `src/synth_datagen/_seed.py` and `src/synth_datagen/_allocations.py`.

#### P2-6  No Hypothesis property tests
- **Evidence:** Grep for `from hypothesis` / `@given` → 0 matches. Master plan Phase 3 requires ≥5 property tests per scenario.
- **Fix:** Phase 3 scope.

#### P2-7  No reproducibility tests for fintech / logistics
- **Evidence:** `tests/test_determinism.py:54,61,79` only covers retail. SaaS v3 has `test_saas_v3_deterministic_core_tables`. `test_fintech_realism.py` and `test_logistics_realism.py` do **not** assert seed→identical output.
- **Fix:** Phase 3: add `test_fintech_reproducibility`, `test_logistics_reproducibility`, `test_kupferkanne_reproducibility` mirroring `test_determinism.py`.

#### P2-8  No CSV roundtrip / byte-equality tests
- **Evidence:** Determinism tests use `pd.testing.assert_frame_equal()` on in-memory DataFrames. No test re-reads exported CSV/Parquet/SQLite and asserts equality.
- **Why P2:** Floating-point formatting / dtype coercion / UTF-8 BOM issues hide here. Master plan baseline-diff procedure (`diff -r baseline_before/ baseline_after/`) operates on file bytes; tests should mirror that contract.
- **Fix:** Phase 3: one test per scenario that runs end-to-end, hashes each output file, and asserts hash equality across runs.

#### P2-9  `SchemaType` enum has dead values (`3nf`, `mixed`)
- **Evidence:** `src/config.py:28-31` declares `NF3 = "3nf"` and `MIXED = "mixed"`, but `src/config.py:254-258` rejects anything other than `STAR` with a runtime ValueError.
- **Fix:** Phase 2: drop the dead enum values + delete the validator branch, OR implement them. README says "Only `--schema star` is supported. `3nf` and `mixed` are rejected explicitly" — so just delete.

#### P2-10  Two `conftest.py` files, root one is a sys.path hack
- **Evidence:** `conftest.py:5` `sys.path.insert(0, str(Path(__file__).parent))`; `tests/conftest.py` then imports `from src.config ...`.
- **Why P2:** Will become unnecessary once src layout is fixed (P1-1). Leaving both during transition is OK.
- **Fix:** Delete root `conftest.py` after `src/synth_datagen/` rename.

#### P2-11  No `examples/` directory but README mentions one
- **Evidence:** README §"Quick Start" links to module-form invocations; `quick_guide_README.md` references `python run_demo.py`. There is a `run_demo.py` at repo root but no `examples/`.
- **Fix:** Phase 4: create `examples/retail_quickstart.py`, `examples/saas_v3_promptforge.py`, etc. Move (or thin-wrap) `run_demo.py` into `examples/`.

#### P2-12  Bandit B608 — SQL string interpolation in `sql_exporter._sql_val`
- **Evidence:** `src/exporters/sql_exporter.py:157` (Medium severity, Low confidence). Hand inspection shows `_sql_val` does single-quote escaping (`'` → `''`) and never interpolates non-stringified values. Effectively safe **for synthetic data only**.
- **Why P2 (not P0):** No untrusted input ever reaches this codepath; the tool generates DDL/DML for self-owned databases. But the construct is fragile — anyone porting `_sql_val` elsewhere is one mistake away from injection.
- **Fix:** Add `# nosec B608` with rationale comment, OR switch to dialect-aware quoting via `sqlalchemy.text` / parametrized inserts.

#### P2-13  Inconsistent column naming convention across exports
- **Evidence:** Classic scenarios export `customer_id`, `order_id` (snake_case). Kupferkanne RFM exports `CustomerID`, `OrderID`, `LineNumber` (PascalCase) per `MEMORY.md` and `kupferkanne_rfm.py`.
- **Why P2:** Mixed conventions surprise downstream consumers. Choose one and document the rationale (Kupferkanne deliberately uses BigQuery `_TABLE_SUFFIX`-friendly names, so this may be intentional).
- **Fix:** Phase 4 README: explicitly document why Kupferkanne diverges. Or normalize.

#### P2-14  Lowest-coverage modules: `parquet_exporter` 27%, `saas_v3/cli` 41%, `main` 66%, `sql_exporter` 72%, `schema_builder` 74%
- **Evidence:** `pytest --cov=src --cov-report=term`.
- **Why P2:** Aggregate is 91% so the project is comfortably above target. But `parquet_exporter.py` at 27% is essentially uncovered; if anyone enables `--export-parquet` they're flying blind.
- **Fix:** Phase 3: add round-trip tests targeting these modules.

---

### P3 — Low (nice to have)

#### P3-1  `run_demo.py` lives at repo root
- **Evidence:** `./run_demo.py` (94 lines).
- **Fix:** Move to `examples/run_demo.py`. Update README + quick guide links.

#### P3-2  `quick_guide_README.md` largely duplicates README.md
- **Evidence:** ~80% command overlap.
- **Fix:** Phase 4: fold useful bits into the new MkDocs site (`docs/quickstart.md`); delete this file.

#### P3-3  Bandit B311 — `random.Random(seed)` flagged as not crypto-safe
- **Evidence:** `src/utils.py:23`. Severity Low. False positive (synthetic-data RNG, never used for crypto).
- **Fix:** `# nosec B311` with comment OR add `bandit` config to skip B311 globally for `src/utils.py`.

#### P3-4  Vulture: unused parameter `unique_cols` in `apply_data_quality`
- **Evidence:** `src/utils.py:337` declared but never read inside the function.
- **Fix:** Either drop the kwarg or wire it through to `inject_duplicates`.

#### P3-5  `Faker.seed(seed)` is called as a classmethod after `Faker()` is instantiated
- **Evidence:** `src/utils.py:25-26`. Works in practice (Faker.seed reseeds the shared `_random_state`), but the pattern is confusing — would be clearer as `faker.seed_instance(seed)`.
- **Fix:** Switch to `faker.seed_instance(seed)`.

#### P3-6  `pyproject.toml` requires-python = `>=3.11` but state tracker says project venv is 3.12
- **Evidence:** `pyproject.toml:9`; master plan §0 §"Pre-flight" note "Python 3.12 via uv-managed venv".
- **Fix:** Decision — either drop 3.11 from CI matrix or bump min to 3.12 to match what's actually tested. Master plan says CI 3.11/3.12/3.13.

#### P3-7  Project `.venv` was empty (no pip, no packages) at audit time
- **Evidence:** `./.venv/Scripts/python.exe -m pip list` → "No module named pip".
- **Why P3:** Doesn't affect the code, but means devs can't run anything until they `pip install -e ".[dev]"`. README documents this; just noting because it cost the auditor a step.
- **Fix:** None required; mention in CONTRIBUTING.md.

#### P3-8  AgentShield baseline scan is config-only (`.claude/`), not source
- **Evidence:** `npx ecc-agentshield scan` scans the `.claude/` directory (Grade A, 2 medium findings about settings.json permission/hook scopes — irrelevant for repo security).
- **Why P3:** Step 5 of audit prompt expected agentshield to surface code-level secrets/credential issues. This tool doesn't actually scan source. Manual `grep` of `src/` for `eval/exec/pickle/yaml.load/shell=True/subprocess` came back **clean**; YAML reads use `yaml.safe_load`/`safe_dump` only.
- **Fix:** None for the code. Optionally add `gitleaks` or `trufflehog` to the CI step in Phase 3 for actual secret scanning.

#### P3-9  Empty `src/__init__.py` and `src/generators/__init__.py`
- **Evidence:** Both files are 1 line / empty.
- **Fix:** After P1-1 rename, populate `src/synth_datagen/__init__.py` with `__version__` and the public `__all__` (Generator/Config/CLI re-exports).

---

## Statistical Correctness Findings

### RNG isolation — current state

| Subsystem | Pattern | Salted? | Status |
|-----------|---------|---------|--------|
| `discounts.py` | `default_rng(seed ^ 0xD15C0UNT)` | yes (`b"D15C0UNT"`) | ✓ correct |
| `saas_v3/engine.py`, `saas_v3/defects.py` | `_seed_from_label(seed, "<concern>")` (hash-based) | yes (per concern) | ✓ correct |
| `kupferkanne_rfm.py:749,990` | `default_rng(seed)` x2 | **no** | ⚠ P1-11 |
| classic generators (`retail`, `saas`, `fintech`, `logistics`) | shared `self.rng` (master) | **no** | ⚠ P0-3 |
| `utils.distribute_counts` fallback | `default_rng(42)` constant | constant | ⚠ P2-4 |

### Distribution correctness

- Beta / log-normal / Pareto parameters work mathematically (clipped, bounded, non-degenerate) but the parameter values are mostly **uncited magic**. See P2-1 for the catalogue.
- One mild risk in `saas.py:204` `bounded_lognormal(3.8, 1.1, 5, 5000)` for employee counts: median ≈ exp(3.8) ≈ 45 employees, top of clip 5000 — plausible for SaaS account distribution but worth a citation.
- `fintech.py:219` `rng.normal(690, 85)` clipped 300-850 for FICO — standard band, reasonable. Worth a comment pointing at the FICO public docs.

### Industry plausibility

- Retail margins 45-65% by segment present (subagent confirmed). ✓
- SaaS NRR / churn / expansion / contraction structurally present in `saas_v3` config defaults but not yet validated against a benchmark assertion (no test computes overall NRR and checks the band).
- No "synthetic fingerprints" detected (uniform churn, flat distributions) — every concern uses Beta/log-normal/weighted-choice.

### Reproducibility (Step 7)

| Scenario | seed=42 run1 vs run2 | Verdict |
|----------|----------------------|---------|
| retail | empty diff | ✓ |
| saas | empty diff | ✓ |
| fintech | empty diff | ✓ |
| logistics | empty diff | ✓ |

Limitation: tests **also** confirm in-memory determinism for retail and saas_v3 only. Add fintech/logistics/kupferkanne tests in Phase 3 (P2-7).

---

## Architecture Findings

### Code metrics (radon CC + MI)

- 106 functions/classes/methods analyzed, **average complexity C (10.92)**.
- 4 functions at rank **D** (worst):
  - `retail_builder._build_orders_and_related`
  - `saas_v3/engine._build_account_month_state`
  - `saas_v3/config.SaaSV3Config.validate_lists`
  - `saas_v3/validate._validate_clean_integrity`
- Maintainability Index: most modules **A**. Three at **C**: `kupferkanne_rfm.py`, `monthly_sales.py`, `saas_v3/engine.py`, `retail_builder.py`. Expected for the larger files; compounding with P2-2 split work.

### Duplication

- `_seed_from_label` × 2 (P2-5)
- `_allocate_counts` × 2 (P2-5)
- per-account row-distribution loop nearly identical between `fintech.py:226-235` and `saas.py:216-228` (subagent finding)
- locale/country dictionaries replicated between `utils.py` and `kupferkanne_rfm.py` (P2-5)

### CLI fragmentation

- Four console scripts (P1-2). Flag conventions diverge:
  - `synthetic-data` defaults `--seed 42`, requires `--scenario`
  - `synthetic-saas` allows `--seed None` (engine-internal default)
  - `synthetic-rfm-kupferkanne` defaults `--seed 42`, requires `--config`
  - `synthetic-monthly-sales` requires `--profile-config` for some flows but not others.

### Public API surface

- `BaseScenarioGenerator` (`src/generators/base.py`) is the contract for the four classic generators — uniformly implemented (subagent confirmed).
- `saas_v3` and `kupferkanne_rfm` do **not** implement this contract; they have their own bespoke entry points. Pharma scenario will have the same temptation.
- No shared protocol for "exporters" either (`csv`, `parquet`, `sql`, `sqlite` exporters share no base class). Fine for now; revisit if a 5th exporter lands.

### Schema-as-data discipline

- `config.py`/`schema_builder.py`/`reporting.py` form a pleasant little engine: tables/relations declared as Pydantic models → topological sort → CSV + DDL + data dictionary + ERD all generated from one source of truth. **This is the strongest part of the codebase** and should be the visible "wow" piece of the README rewrite in Phase 4.

---

## Security Findings

| Tool | Finding | Severity | Verdict |
|------|---------|----------|---------|
| bandit | B608 SQL string interpolation in `sql_exporter.py:157` | Medium / Low confidence | False positive (synthetic data, escaped); see P2-12 |
| bandit | B311 `random.Random(seed)` | Low / High confidence | False positive (synthetic RNG, not crypto); see P3-3 |
| pip-audit | 0 vulnerabilities in declared deps | — | ✓ |
| AgentShield | 2 Medium on `.claude/settings.json` (config-only) | Medium | Out of scope for repo security; see P3-8 |
| Manual grep | `eval`, `exec`, `pickle`, `yaml.load`, `shell=True`, `subprocess`, `os.system` | — | **0 hits in `src/`** ✓ |
| Manual grep | `yaml.safe_load`/`yaml.safe_dump` only | — | ✓ all YAML reads are safe |
| Git history | Hardcoded secrets / API keys | — | None visible (3 commits total: `0e27721`, `d954b50`, `eedaa1d`) |

**Bottom line:** the source is security-clean for its purpose (offline data generation). The bandit Medium is worth a `# nosec` rationale comment. No P0/P1 security findings.

---

## Documentation Gaps

- **README.md (277 lines):** thorough on commands, but mixes audience (developer + analyst + agent). Some references are project-internal ("v3 copy", "the original `synthetic_data` repo remains untouched"). Phase 4 rewrite is in master plan.
- **No `docs/` directory.** No MkDocs site (Phase 4 deliverable).
- **No CHANGELOG / CONTRIBUTING / SECURITY.** (P1-3)
- **No LICENSE.** (P0-1)
- **No `examples/` directory.** (P2-11)
- **`AGENTS.md` is generic Codex doc.** (P1-7)
- **`MEMORY.md` is internal scratchpad.** (P1-8)
- **`quick_guide_README.md` duplicates README.** (P3-2)
- **Auto-generated docs (`data_dictionary.md`, `erd.md`) are written per-run and look good** — but neither is sample-checked into the repo. Adding one frozen sample under `docs/sample_outputs/` would help showcase what the tool produces.
- **Public docstrings are sparse:** `src/utils.py` is well-commented; `src/generators/*.py` and `src/saas_v3/engine.py` rely on context — no module docstrings on most generator methods.

---

## Recommended Refactor Plan (value-per-hour ordered)

> Each item is a candidate for one Phase 2 / Phase 3 / Phase 4 commit. Time estimates are rough.

1. **(30 min, Phase 2)** P1-10 + P2-9 — apply `ruff format .` + delete dead `SchemaType` enum values. Behavior-neutral, baseline-diff-empty, gets the floor clean.
2. **(2 h, Phase 2)** P0-2 + P1-1 — rename to `synth-datagen`, restructure to `src/synth_datagen/` layout, version bump to `0.2.0-dev`. **Run baseline-diff before and after each step** (output bytes must be identical aside from manifest paths). This is the riskiest commit; do it early.
3. **(3 h, Phase 2)** P0-3 + P1-11 + P2-4 + P2-5 — extract `src/synth_datagen/rng.py` factory, register all salts (D15C0UNT existing + KUPFER_* + SAAS_* + RETAIL_* + LOGISTICS_* + FINTECH_*), migrate every `np.random.default_rng(...)` and `_seed_from_label` call site. **Baseline-diff must stay empty** — choose salts so the very first migration commit reproduces today's bytes (use the existing D15C0UNT for discounts; for the master streams, the salt is `0` initially, then change to a real salt only when the new concern is added in Phase 5/6).
4. **(2 h, Phase 2)** P1-2 — single Typer app `synth-datagen` with sub-commands. Keep old console-script names as aliases.
5. **(1 h, Phase 2)** P0-1 + P1-6 — LICENSE (MIT) + pyproject metadata pass.
6. **(2 h, Phase 2)** P2-2 — split the four `D`-rank functions. TDD: capture current behavior in characterization tests first, then extract.
7. **(1 h, Phase 2)** P1-9 — fix the real mypy bugs (`utils.py:256`, `monthly_sales.py:394-395 redefinition`, abstract-class instantiation in `pipeline.py:45`); add `types-PyYAML` to dev deps.
8. **(2 h, Phase 2)** P2-1 + P2-3 — extract `src/synth_datagen/benchmarks/` and `src/synth_datagen/distributions.py`. Citations as comments.
9. **(1 h, Phase 2)** P1-5 + P2-12 + P3-3 — `.pre-commit-config.yaml` (ruff + mypy + bandit) with rationale comments for B311/B608.
10. **(3 h, Phase 3)** P2-6 — Hypothesis property tests, ≥5 per scenario.
11. **(2 h, Phase 3)** P2-7 + P2-8 — fintech/logistics/kupferkanne reproducibility tests + CSV roundtrip / file-hash tests.
12. **(2 h, Phase 3)** P1-4 — `.github/workflows/ci.yml` for Python 3.11/3.12/3.13.
13. **(1 h, Phase 3)** P1-12 — shrink slow fixtures, add `@pytest.mark.slow`, target `pytest -q < 60s` default run.
14. **(2 h, Phase 4)** P1-3 — CHANGELOG, CONTRIBUTING, SECURITY.
15. **(1 h, Phase 4)** P1-7 + P1-8 + P3-2 — purge AGENTS.md (or rewrite), `.gitignore` MEMORY.md, fold `quick_guide_README.md` into MkDocs.
16. **(3 h, Phase 4)** README rewrite + MkDocs site + `examples/` directory (P2-11 + P3-1 — move `run_demo.py`).
17. **(remainder)** P3 items absorbed opportunistically.

**Estimated Phase 2 total:** 12-14 h agent + 1 h human review (matches master plan budget).
**Estimated Phase 3 total:** 8-10 h agent + 30 min human review.
**Estimated Phase 4 total:** 6-8 h agent + 30 min human review.

---

## Files Touched in Phase 2 (Preview)

- **All of them**, due to the rename / reformatting / RNG-factory migration. Specifically:
  - `pyproject.toml` (P0-1, P0-2, P1-6, P1-9 dev deps)
  - `src/__init__.py` → `src/synth_datagen/__init__.py` + `__version__` (P0-2, P1-1, P3-9)
  - new `src/synth_datagen/rng.py` (P0-3)
  - new `src/synth_datagen/benchmarks/{retail,saas,fintech,logistics}.py` (P2-1, P2-3)
  - new `src/synth_datagen/distributions.py` (P2-3)
  - all `src/generators/*.py` (RNG factory migration, function splits, magic-number extraction)
  - `src/saas_v3/engine.py`, `src/saas_v3/defects.py`, `src/saas_v3/config.py`, `src/saas_v3/validate.py` (RNG factory + function splits)
  - `src/kupferkanne_rfm.py`, `src/kupferkanne_rfm_config.py` (RNG factory + locale dedup)
  - `src/main.py` → unified Typer app (P1-2)
  - `src/utils.py` (P1-9 type bug, P2-4 fail-on-None rng, P3-4 unused arg, P3-5 faker.seed_instance)
  - `src/config.py` (P2-9 dead enums)
  - `src/exporters/sql_exporter.py` (P2-12 nosec rationale)
  - delete root `conftest.py` after rename (P2-10)
  - all `tests/test_*.py` import-path updates
  - new `LICENSE` (P0-1)
  - new `.pre-commit-config.yaml` (P1-5)
  - delete or rewrite `AGENTS.md`, `MEMORY.md`, `quick_guide_README.md` — Phase 4

---

## Notes for the human reviewer (you)

- **Reproducibility verified for all 4 classic scenarios** under seed=42 with shrunken row counts. SaaS v3 and Kupferkanne RFM not re-run in this audit but their existing tests confirm in-memory determinism.
- **No P0 statistical or security bugs.** The three P0s are publication-blockers (license/name/RNG-future-fragility), not "data is wrong" issues.
- **Phase 2 GO recommendation:** GO. The list is long but mostly mechanical. The one finding that requires a real architectural decision is **P0-3 RNG factory** — please skim that section before the Phase 2 session starts; it constrains how P5 (SaaS sub-modes) and P6 (Pharma) can be added without breaking baseline diffs.
- **Skip-able in Phase 2 if time-pressed:** P2-2 (function splits), P2-13 (naming convention doc), P3-* items. Defer to Phase 4 or future-work section in README.
- **Do NOT skip in Phase 2:** P0-1, P0-2, P0-3, P1-1, P1-2, P1-9 (the real bugs only), P1-11, P2-4, P2-9. These are pre-requisites for Phase 5/6.

---

*End of audit report. Phase 1 read-only; no source files modified. Author: Claude Code (Opus 4.7). Next action: human reviewer reads this report, marks findings to address in Phase 2 in the addressed_in_phase2 list (master doc Section 11), and runs the Phase 2 prompt.*
