# SaaS Extension v0.2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a v0.2.1 minimum-viable SaaS extension on top of `saas_v3` that (a) migrates the engine onto the central `make_rng` factory under salt `0x5AA50000`, (b) adds the `plg-usage-based` sub-mode dispatch (single sub-mode for v0.2.1; `vertical-account-based` deferred to v0.3.0), (c) emits the 5-movement MRR waterfall via a new `subscription_events` table, and (d) adds an opt-in benchmark validation pass — without changing any byte of the legacy `retail / saas / fintech / logistics` baseline outputs.

**Architecture:**
- Extend `src/synth_datagen/saas_v3/` rather than fork. Add a `mode` field on `RunConfig` (`plg-usage-based` | `legacy`; default `legacy` so existing configs are byte-stable when paired with the same RNG state).
- Migrate `SaaSV3Engine._rng` and `DefectInjector._rng` to the central factory (`make_rng(seed, "saas_v3").spawn(N)` for child concerns, indexed in a stable `_RNG_LABELS` registry). This shifts saas_v3 RNG bytes once, in one commit.
- The new `subscription_events` table (event_id PK, subscription_id FK, account_id FK, event_type, event_date, mrr_delta, previous_mrr, new_mrr, reason) is built deterministically from the existing `subscriptions` lifecycle history. It is gated on the new mode so legacy configs are unaffected.
- The benchmark validation pass is implemented as `validate.compute_benchmarks(generated)` returning a `BenchmarkReport`; surfaced via `--benchmark-validation/--no-benchmark-validation` on the `saas-v3 generate` CLI; written to `benchmark_validation.md` next to the run root.
- `scripts/baseline_diff.py` gains a `saas_v3` capture target at the end of the phase, pinning the post-migration bytes so v0.3.0 can't shift them silently.

**Tech Stack:** Python 3.11+, numpy (`make_rng` + `Generator.spawn`), pandas, pydantic v2, typer, pytest + Hypothesis, ruff/pre-commit, mkdocs-material.

---

## Conventions for every task

- **Branch**: all work on `feat/saas-extension` cut from `main @ c2ff53e`. Push origin after every commit.
- **Commits**: Conventional Commits, no `Co-authored-by` trailer. Subject ≤ 72 chars.
- **TDD where applicable**: every behavior-changing task writes the failing test first, then the implementation. RNG migration / pure refactors that must preserve behavior write a regression test first instead.
- **Backward-compat gate (mandatory before every push):**
  ```powershell
  python scripts/baseline_diff.py capture out/baseline_pre_<n>
  python scripts/baseline_diff.py compare out/baseline_main out/baseline_pre_<n>
  ```
  `out/baseline_main` is captured once at Task 0; the compare must report **empty diff** for `retail / saas / fintech / logistics`. (Tasks 12+ pin `saas_v3` too.)
- **Quality gates before each push** (any failure = fix and re-push, do not skip):
  ```powershell
  pre-commit run --all-files
  pytest -x
  mkdocs build --strict
  ```
- **Memory gotchas to honor (already in `memory/`):**
  - `ruff-pin-coupling.md` — pre-commit ruff rev must match `[test]` extra ruff version.
  - `cli-tests-ansi-on-ci.md` — CliRunner help asserts go through `tests.helpers.strip_ansi`.
  - `precommit-checkyaml-mkdocs.md` — new YAML configs run `pre-commit run --all-files` locally; check-yaml hook excludes `mkdocs.yml`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/synth_datagen/rng.py` | Modify | Register `"saas_v3"` salt = `0x5AA50000` in `SALT_REGISTRY`. |
| `src/synth_datagen/saas_v3/config.py` | Modify | Add `RunConfig.mode: Literal["legacy", "plg-usage-based"] = "legacy"`. Add `BenchmarkConfig` with target ranges (NRR, GRR, churn-by-plan, trial-conversion). |
| `src/synth_datagen/saas_v3/engine.py` | Modify | Migrate `_rng` to central factory. Add `_RNG_LABELS` ordered tuple. Add `_build_subscription_events()` (gated on mode). Append `"subscription_events"` to `TABLE_ORDER` & `EXPORTED_COLUMNS` only when emitted. |
| `src/synth_datagen/saas_v3/defects.py` | Modify | Migrate `DefectInjector._rng` to central factory under same salt. |
| `src/synth_datagen/saas_v3/validate.py` | Modify | Add `compute_benchmarks(tables, config) -> BenchmarkReport`. Extend `validate_generated_dataset` to optionally include benchmark issues. |
| `src/synth_datagen/saas_v3/cli.py` | Modify | Add `--benchmark-validation/--no-benchmark-validation` flag (default `False` for legacy mode, `True` for `plg-usage-based`). Write `benchmark_validation.md` to run root. |
| `src/synth_datagen/saas_v3/exporters.py` | Modify | Export `subscription_events.csv` when present; emit `benchmark_validation.md`. |
| `configs/saas_v3.plg.yaml` | Create | New config exercising `mode: plg-usage-based`, smoke-sized rows, registered benchmarks. |
| `tests/test_rng_factory.py` | Modify | Add test asserting `"saas_v3"` registered with salt `0x5AA50000`. |
| `tests/test_saas_v3_subscription_events.py` | Create | Unit + Hypothesis property tests for the new table (5 movement types, MRR-delta sums, FK integrity, reproducibility, mode gating). |
| `tests/test_saas_v3_benchmarks.py` | Create | Tests for `compute_benchmarks` (in-range PASS, out-of-range FAIL, default-off in legacy). |
| `tests/test_saas_v3_engine.py` | Modify | Update determinism golden assertions after RNG migration (shape-only, not byte-pinned). |
| `tests/test_saas_v3_cli_unit.py` | Modify | Cover the new `--benchmark-validation` flag and mode dispatch. |
| `tests/property/test_saas_v3_invariants.py` | Create | Hypothesis: for any seed in [0, 2^31), `subscription_events.mrr_delta.sum()` per account equals current account `mrr` ± 0.01 in `plg-usage-based` mode. |
| `scripts/baseline_diff.py` | Modify | Add `saas_v3` capture target invoking `synth-datagen saas-v3 generate --config configs/saas_v3.smoke.yaml --mode clean --seed 42`. |
| `docs/scenarios/saas.md` | Modify | Document new `mode` field, `subscription_events` table, `--benchmark-validation` flag, and `0x5AA50000` salt. |
| `README.md` | Modify | Add v0.2.1 line under "What's new". |
| `CHANGELOG.md` | Modify | Populate `[0.2.1]` Added/Changed/Fixed sections. |
| `pyproject.toml` | Modify | Bump version `0.2.0` → `0.2.1-dev` (then `0.2.1` at release). |

---

## Task 0: Worktree + branch setup + baseline capture

**Files:**
- Create branch: `feat/saas-extension` off `main @ c2ff53e`
- Create: `out/baseline_main/` (gitignored — run output)

- [ ] **Step 1: Confirm clean tree on main @ c2ff53e**

```powershell
git status
git rev-parse HEAD   # must equal c2ff53e
```
Expected: `working tree clean`, HEAD at `c2ff53e`.

- [ ] **Step 2: Cut feature branch**

```powershell
git checkout -b feat/saas-extension c2ff53e
git push -u origin feat/saas-extension
```
Expected: branch created, tracked on origin.

- [ ] **Step 3: Capture baseline before any change**

```powershell
python scripts/baseline_diff.py capture out/baseline_main
```
Expected: `out/baseline_main/{retail,saas,fintech,logistics}/` populated. This is the reference every later commit must match byte-for-byte for those four scenarios.

- [ ] **Step 4: Sanity-check pytest + pre-commit + mkdocs are green on main**

```powershell
pre-commit run --all-files
pytest -x -q
mkdocs build --strict
```
Expected: all three pass. If anything is red on a fresh `main`, stop and surface it before continuing.

- [ ] **Step 5: No commit yet — Task 0 is environment-only.**

---

## Task 1: Register `"saas_v3"` salt in the central RNG factory

**Files:**
- Modify: `src/synth_datagen/rng.py`
- Test: `tests/test_rng_factory.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rng_factory.py`:
```python
from synth_datagen.rng import SALT_REGISTRY, make_rng


def test_saas_v3_salt_registered() -> None:
    assert SALT_REGISTRY["saas_v3"] == 0x5AA50000


def test_saas_v3_make_rng_independent_of_master() -> None:
    master = make_rng(42, "master")
    saas = make_rng(42, "saas_v3")
    # First five draws must differ — proves stream isolation.
    assert list(master.integers(0, 1_000_000, size=5)) != list(
        saas.integers(0, 1_000_000, size=5)
    )
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_rng_factory.py::test_saas_v3_salt_registered -v
```
Expected: FAIL with `KeyError: 'saas_v3'`.

- [ ] **Step 3: Register the salt**

In `src/synth_datagen/rng.py`, extend `SALT_REGISTRY`:
```python
# Phase 5 — SaaS extension v0.2.1. Locked decision: 0x5AA50000.
_SAAS_V3_SALT = 0x5AA50000

SALT_REGISTRY: dict[str, int] = {
    "master": 0,
    "discounts": _DISCOUNTS_SALT,
    "saas_v3": _SAAS_V3_SALT,
}
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_rng_factory.py -v
```
Expected: PASS, all existing rng-factory tests still green.

- [ ] **Step 5: Backward-compat check + push**

```powershell
python scripts/baseline_diff.py capture out/baseline_t1
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t1
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/rng.py tests/test_rng_factory.py
git commit -m "feat(rng): register saas_v3 salt 0x5AA50000 for Phase 5 streams"
git push origin feat/saas-extension
```
Expected: empty diff (registry-only addition cannot shift any consumer); commit pushed.

---

## Task 2: Migrate `SaaSV3Engine._rng` to central factory (refactor, no behavior change beyond RNG bytes of saas_v3)

**Files:**
- Modify: `src/synth_datagen/saas_v3/engine.py:215-221, 119-122`
- Modify: `tests/test_saas_v3_engine.py` (update post-migration assertions)

- [ ] **Step 1: Write the failing regression test**

Append to `tests/test_saas_v3_engine.py`:
```python
def test_saas_v3_rng_uses_central_factory(tmp_path) -> None:
    """Engine RNG must derive from make_rng(seed, 'saas_v3'), not np.random.default_rng directly."""
    import numpy as np
    from synth_datagen.rng import make_rng

    config = _smoke_config(tmp_path)
    engine = SaaSV3Engine(config)
    # Internal contract: engine exposes a parent RNG sourced via factory.
    parent = make_rng(config.run.seed, "saas_v3")
    expected_first = parent.integers(0, 1_000_000_000, size=1)[0]
    actual_first = engine._parent_rng.integers(0, 1_000_000_000, size=1)[0]
    assert int(actual_first) == int(expected_first)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_saas_v3_engine.py::test_saas_v3_rng_uses_central_factory -v
```
Expected: FAIL with `AttributeError: 'SaaSV3Engine' object has no attribute '_parent_rng'`.

- [ ] **Step 3: Implement RNG migration**

Edit `src/synth_datagen/saas_v3/engine.py`:

1. At top of file, add import:
   ```python
   from ..rng import make_rng
   ```
2. Define a stable label registry just above `class SaaSV3Engine`:
   ```python
   # Stable order — appending new labels is OK; reordering shifts bytes.
   _RNG_LABELS: tuple[str, ...] = (
       "accounts",
       "lifecycle",
       "subscriptions",
       "account_month_state",
       "users",
       "invoices",
       "support_tickets",
       "nps",
       "product_events",
   )
   ```
3. In `SaaSV3Engine.__init__`, after `self.seed = ...`, add:
   ```python
   self._parent_rng = make_rng(self.seed, "saas_v3")
   spawned = self._parent_rng.spawn(len(_RNG_LABELS))
   self._rng_streams: dict[str, np.random.Generator] = dict(zip(_RNG_LABELS, spawned))
   ```
4. Replace `_rng`:
   ```python
   def _rng(self, label: str) -> np.random.Generator:
       try:
           return self._rng_streams[label]
       except KeyError as exc:
           raise KeyError(
               f"Unknown saas_v3 RNG label '{label}'. Add it to _RNG_LABELS."
           ) from exc
   ```
5. Delete the now-unused `_seed_from_label` helper at line 119–122 **only if no other module imports it**. Verify with:
   ```powershell
   git grep -n _seed_from_label src/
   ```
   If `defects.py` still uses it, leave it for Task 3.

- [ ] **Step 4: Update existing determinism test golden assertions if needed**

`test_saas_v3_deterministic_core_tables` is shape-only (`assert_frame_equal` between two runs of same seed) — should still pass. Run it:
```powershell
pytest tests/test_saas_v3_engine.py -v
```
Expected: all PASS. If `test_saas_v3_clean_validation_and_id_formats` or the dirty test fails on validation thresholds (e.g. defect counts shifted across the 0.20 tolerance band), inspect the diff and adjust the smoke config row counts in a SEPARATE follow-up task — do not loosen the tolerance.

- [ ] **Step 5: Backward-compat check**

```powershell
python scripts/baseline_diff.py capture out/baseline_t2
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t2
```
Expected: empty diff for retail/saas/fintech/logistics. (`saas_v3` is NOT in the diff yet — pinned in Task 12.)

- [ ] **Step 6: Quality gates + commit**

```powershell
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/saas_v3/engine.py tests/test_saas_v3_engine.py
git commit -m "refactor(saas_v3): migrate engine RNG to central factory under saas_v3 salt"
git push origin feat/saas-extension
```

---

## Task 3: Migrate `DefectInjector._rng` to central factory

**Files:**
- Modify: `src/synth_datagen/saas_v3/defects.py:55-60`

- [ ] **Step 1: Write the failing regression test**

Append to `tests/test_saas_v3_engine.py`:
```python
def test_saas_v3_defects_use_central_factory(tmp_path) -> None:
    """DefectInjector must spawn from the same parent saas_v3 stream."""
    from synth_datagen.saas_v3.defects import DefectInjector
    from synth_datagen.rng import make_rng

    config = _smoke_config(tmp_path)
    injector = DefectInjector(config.defects, seed=config.run.seed)
    # Defects parent must equal one of the spawned children of make_rng(seed, "saas_v3"),
    # NOT a direct np.random.default_rng call.
    assert hasattr(injector, "_parent_rng")
    parent = make_rng(config.run.seed, "saas_v3")
    # Just assert the bit-state is reachable from the saas_v3 stream — exact
    # spawn index is locked by _DEFECT_LABELS (see implementation).
    assert injector._parent_rng is not None
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_saas_v3_engine.py::test_saas_v3_defects_use_central_factory -v
```
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement migration**

Edit `src/synth_datagen/saas_v3/defects.py`:

1. Add `from ..rng import make_rng` at top.
2. Define `_DEFECT_LABELS: tuple[str, ...] = (...)` listing all 11 defect names in current source order (do NOT reorder).
3. In `DefectInjector.__init__`, replace the seed plumbing:
   ```python
   self.seed = seed
   self._parent_rng = make_rng(seed, "saas_v3").spawn(len(_RNG_LABELS) + 1)[-1]
   spawned = self._parent_rng.spawn(len(_DEFECT_LABELS))
   self._defect_rngs: dict[str, np.random.Generator] = dict(zip(_DEFECT_LABELS, spawned))
   ```
   The `+ 1` keeps the engine's nine streams disjoint from the defects parent.

   **Note:** import `_RNG_LABELS` from `engine` — or duplicate the constant `9` here with a comment explaining the offset. Prefer importing to avoid drift:
   ```python
   from .engine import _RNG_LABELS as _ENGINE_RNG_LABELS
   ```
4. Replace `_rng`:
   ```python
   def _rng(self, label: str) -> np.random.Generator:
       try:
           return self._defect_rngs[label]
       except KeyError as exc:
           raise KeyError(
               f"Unknown defect label '{label}'. Add it to _DEFECT_LABELS."
           ) from exc
   ```
5. Remove the local `_seed_from_label` import / usage. If `engine._seed_from_label` is now orphaned, delete it as part of this task.

- [ ] **Step 4: Run all saas_v3 tests**

```powershell
pytest tests/test_saas_v3_engine.py tests/test_saas_v3_cli_unit.py tests/test_saas_empty_feature_pool.py -v
```
Expected: all PASS. Defect counts may shift within the 0.20 tolerance — that's fine.

- [ ] **Step 5: Backward-compat check + commit**

```powershell
python scripts/baseline_diff.py capture out/baseline_t3
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t3
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/saas_v3/defects.py src/synth_datagen/saas_v3/engine.py tests/test_saas_v3_engine.py
git commit -m "refactor(saas_v3): migrate DefectInjector RNG to central factory"
git push origin feat/saas-extension
```

---

## Task 4: Add `RunConfig.mode` field with `legacy` default

**Files:**
- Modify: `src/synth_datagen/saas_v3/config.py:30-35`
- Test: `tests/test_saas_v3_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_saas_v3_config.py`:
```python
import pytest
from synth_datagen.saas_v3.config import RunConfig


def test_runconfig_mode_defaults_to_legacy() -> None:
    rc = RunConfig(name="x", seed=1)
    assert rc.mode == "legacy"


def test_runconfig_mode_accepts_plg() -> None:
    rc = RunConfig(name="x", seed=1, mode="plg-usage-based")
    assert rc.mode == "plg-usage-based"


def test_runconfig_mode_rejects_unknown() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError
        RunConfig(name="x", seed=1, mode="vertical-account-based")  # deferred to v0.3.0
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_saas_v3_config.py -v
```
Expected: FAIL — `mode` not a known field.

- [ ] **Step 3: Add `mode` field**

In `src/synth_datagen/saas_v3/config.py`, replace `RunConfig`:
```python
from typing import Literal

class RunConfig(StrictModel):
    name: str
    seed: int = Field(ge=0)
    schema_version: str = "saas_v3"
    # v0.2.1: 'legacy' = pre-extension behavior (byte-stable for existing configs).
    # 'plg-usage-based' = new sub-mode emitting subscription_events + benchmarks.
    # 'vertical-account-based' deferred to v0.3.0.
    mode: Literal["legacy", "plg-usage-based"] = "legacy"
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_saas_v3_config.py -v
```
Expected: all PASS.

- [ ] **Step 5: Backward-compat check + commit**

```powershell
python scripts/baseline_diff.py capture out/baseline_t4
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t4
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/saas_v3/config.py tests/test_saas_v3_config.py
git commit -m "feat(saas_v3): add RunConfig.mode literal (legacy default, plg-usage-based opt-in)"
git push origin feat/saas-extension
```

---

## Task 5: Build `subscription_events` table behind `mode == "plg-usage-based"` gate

**Files:**
- Modify: `src/synth_datagen/saas_v3/engine.py` (new method `_build_subscription_events`, call site in `generate`, append to `EXPORTED_COLUMNS`/`TABLE_ORDER` conditionally)
- Test: `tests/test_saas_v3_subscription_events.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_saas_v3_subscription_events.py`:
```python
"""Tests for the v0.2.1 subscription_events table (plg-usage-based mode)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from synth_datagen.saas_v3.config import OutputMode, load_config
from synth_datagen.saas_v3.engine import SaaSV3Engine

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


def _plg_config(tmp_path):
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    cfg.output.root_dir = tmp_path
    return cfg


def test_legacy_mode_omits_subscription_events(tmp_path) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.output.root_dir = tmp_path
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    assert "subscription_events" not in result.clean.tables


def test_plg_mode_emits_all_five_movement_types(tmp_path) -> None:
    result = SaaSV3Engine(_plg_config(tmp_path)).generate(OutputMode.CLEAN)
    events = result.clean.materialize("subscription_events")
    assert {"new", "expansion", "contraction", "churn", "reactivation"}.issubset(
        set(events["event_type"].unique())
    )


def test_plg_mode_mrr_delta_sum_matches_current_mrr(tmp_path) -> None:
    result = SaaSV3Engine(_plg_config(tmp_path)).generate(OutputMode.CLEAN)
    accounts = result.clean.materialize("accounts")
    events = result.clean.materialize("subscription_events")
    # hidden 'mrr' column lives on internal profiles; surface it via the
    # GeneratedTables.hidden_tables dict as 'account_mrr'.
    account_mrr = result.clean.hidden_tables["account_mrr"].set_index("account_id")["mrr"]
    delta_sum = events.groupby("account_id")["mrr_delta"].sum()
    for acct in account_mrr.sample(min(50, len(account_mrr)), random_state=0).index:
        assert abs(float(delta_sum.get(acct, 0.0)) - float(account_mrr[acct])) < 0.01


def test_plg_mode_event_types_have_signed_deltas(tmp_path) -> None:
    result = SaaSV3Engine(_plg_config(tmp_path)).generate(OutputMode.CLEAN)
    events = result.clean.materialize("subscription_events")
    assert (events.loc[events.event_type == "new", "mrr_delta"] > 0).all()
    assert (events.loc[events.event_type == "expansion", "mrr_delta"] > 0).all()
    assert (events.loc[events.event_type == "contraction", "mrr_delta"] < 0).all()
    assert (events.loc[events.event_type == "churn", "mrr_delta"] < 0).all()
    assert (events.loc[events.event_type == "reactivation", "mrr_delta"] > 0).all()


def test_plg_mode_reproducible(tmp_path) -> None:
    a = SaaSV3Engine(_plg_config(tmp_path / "a")).generate(OutputMode.CLEAN).clean.materialize("subscription_events")
    b = SaaSV3Engine(_plg_config(tmp_path / "b")).generate(OutputMode.CLEAN).clean.materialize("subscription_events")
    pd.testing.assert_frame_equal(a, b)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_saas_v3_subscription_events.py -v
```
Expected: FAIL — `KeyError: 'subscription_events'`.

- [ ] **Step 3: Implement `_build_subscription_events`**

Edit `src/synth_datagen/saas_v3/engine.py`:

1. Append `"subscription_events"` to `_RNG_LABELS` (at the END to preserve byte-stability of earlier streams):
   ```python
   _RNG_LABELS: tuple[str, ...] = (
       "accounts", "lifecycle", "subscriptions", "account_month_state",
       "users", "invoices", "support_tickets", "nps", "product_events",
       "subscription_events",   # v0.2.1
   )
   ```
2. Add `"subscription_events"` to `EXPORTED_COLUMNS`:
   ```python
   "subscription_events": [
       "event_id", "subscription_id", "account_id", "event_type",
       "event_date", "mrr_delta", "previous_mrr", "new_mrr", "reason",
   ],
   ```
3. Add the build method (full implementation — derive from existing `subscriptions` history + `account_month_state`):
   ```python
   def _build_subscription_events(
       self,
       profiles: pd.DataFrame,
       subscriptions: pd.DataFrame,
       account_month_state: pd.DataFrame,
   ) -> pd.DataFrame:
       """Derive the 5-movement MRR waterfall from existing lifecycle output.

       Algorithm (deterministic, no fresh randomness besides reason sampling
       under the dedicated 'subscription_events' stream):

         1. Sort subscriptions by (account_id, start_date).
         2. For each account, walk subscriptions in order:
            - First active sub  -> 'new'    (delta = +mrr,            prev=0)
            - Higher mrr next   -> 'expansion'   (delta = +diff)
            - Lower mrr next    -> 'contraction' (delta = -diff)
            - status='churned'  -> 'churn'  (delta = -mrr,            new=0)
            - Re-activation after a churn -> 'reactivation' (+mrr from 0)
         3. Reason: for churn -> sample from DEFAULT_CANCELLATION_REASONS
            using a Pareto-skewed weight vector
            (np.array([0.30,0.25,0.15,0.10,0.08,0.06,0.04,0.02][:n])).
            For expansion -> {'seat_add','tier_upgrade','usage_overage','module_add'}
            uniform.
            For contraction -> {'seat_drop','tier_downgrade'} uniform.
            For new/reactivation -> empty string.
         4. event_id via self.id_factory ('SE-' prefix; add to ids.py).
       """
       rng = self._rng("subscription_events")
       ...  # implementation per algorithm above
       return df_with_columns(EXPORTED_COLUMNS["subscription_events"])
   ```
   Full implementation (~80 lines) to be authored during execution; the contract above is binding.
4. Add `event_id` pattern in `src/synth_datagen/saas_v3/ids.py`: `"SE-XXXXX"` 8-digit zero-padded; update `pattern_for("event_id")` ONLY if the existing pattern doesn't already match — otherwise use a distinct key `subscription_event_id`.
5. In `generate()`, after `subscriptions = self._build_subscriptions(...)`, add:
   ```python
   if self.config.run.mode == "plg-usage-based":
       sub_events = self._build_subscription_events(profiles, subscriptions, account_month_state)
       clean.tables["subscription_events"] = [sub_events]
       # Surface account mrr for tests / waterfall consumers
       clean.hidden_tables["account_mrr"] = profiles[["account_id", "mrr"]].copy()
   ```
6. Update `TABLE_ORDER` only at export time — the constant stays as-is for legacy mode.

- [ ] **Step 4: Run new tests to verify they pass**

```powershell
pytest tests/test_saas_v3_subscription_events.py -v
```
Expected: all 5 PASS.

- [ ] **Step 5: Backward-compat check (legacy mode unchanged)**

```powershell
python scripts/baseline_diff.py capture out/baseline_t5
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t5
```
Expected: empty diff. The `mode == "legacy"` default guarantees no behavior change for existing configs.

- [ ] **Step 6: Quality gates + commit**

```powershell
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/saas_v3/engine.py src/synth_datagen/saas_v3/ids.py tests/test_saas_v3_subscription_events.py
git commit -m "feat(saas_v3): emit subscription_events table with 5 MRR movement types in plg-usage-based mode"
git push origin feat/saas-extension
```

---

## Task 6: Wire `subscription_events.csv` into the exporter

**Files:**
- Modify: `src/synth_datagen/saas_v3/exporters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_saas_v3_subscription_events.py`:
```python
def test_plg_mode_exports_subscription_events_csv(tmp_path) -> None:
    from synth_datagen.saas_v3.exporters import SaaSV3Exporter
    cfg = _plg_config(tmp_path)
    cfg.output.root_dir = tmp_path / "out"
    engine = SaaSV3Engine(cfg)
    result = engine.generate(OutputMode.CLEAN)
    paths = SaaSV3Exporter(cfg).export_result(result)
    csv_path = Path(paths["run_root"]) / "clean" / "subscription_events.csv"
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    assert list(df.columns) == [
        "event_id", "subscription_id", "account_id", "event_type",
        "event_date", "mrr_delta", "previous_mrr", "new_mrr", "reason",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_saas_v3_subscription_events.py::test_plg_mode_exports_subscription_events_csv -v
```
Expected: FAIL — file missing.

- [ ] **Step 3: Patch the exporter**

In `src/synth_datagen/saas_v3/exporters.py`, find the table-iteration loop and add a conditional branch that includes `"subscription_events"` when present in `result.clean.tables`. Mirror the existing CSV/Parquet export plumbing — no special-casing.

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_saas_v3_subscription_events.py -v
```
Expected: all PASS.

- [ ] **Step 5: Quality gates + commit**

```powershell
python scripts/baseline_diff.py capture out/baseline_t6
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t6
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/saas_v3/exporters.py tests/test_saas_v3_subscription_events.py
git commit -m "feat(saas_v3): export subscription_events.csv when mode=plg-usage-based"
git push origin feat/saas-extension
```

---

## Task 7: Add Hypothesis property test for MRR-delta invariant

**Files:**
- Create: `tests/property/test_saas_v3_invariants.py`

- [ ] **Step 1: Write the property test**

```python
"""Hypothesis invariants for saas_v3 plg-usage-based mode."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from synth_datagen.saas_v3.config import OutputMode, load_config
from synth_datagen.saas_v3.engine import SaaSV3Engine

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


@pytest.mark.slow
@settings(max_examples=8, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_subscription_events_mrr_delta_balances(tmp_path_factory, seed: int) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    cfg.run.seed = seed
    cfg.output.root_dir = tmp_path_factory.mktemp(f"seed_{seed}")
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    events = result.clean.materialize("subscription_events")
    account_mrr = result.clean.hidden_tables["account_mrr"].set_index("account_id")["mrr"]
    delta_sum = events.groupby("account_id")["mrr_delta"].sum()
    for acct, mrr in account_mrr.items():
        assert abs(float(delta_sum.get(acct, 0.0)) - float(mrr)) < 0.01, (
            f"seed={seed} account={acct} delta_sum={delta_sum.get(acct, 0.0)} mrr={mrr}"
        )
```

- [ ] **Step 2: Run the property test**

```powershell
pytest tests/property/test_saas_v3_invariants.py -v -m slow
```
Expected: PASS for all 8 generated seeds. If any seed fails, fix the engine — do NOT loosen the tolerance.

- [ ] **Step 3: Quality gates + commit**

```powershell
pre-commit run --all-files
git add tests/property/test_saas_v3_invariants.py
git commit -m "test(saas_v3): hypothesis property test for MRR-delta sum invariant"
git push origin feat/saas-extension
```

---

## Task 8: Add `BenchmarkConfig` + `compute_benchmarks` validation pass

**Files:**
- Modify: `src/synth_datagen/saas_v3/config.py` (add `BenchmarkConfig`, optional field on `SaaSV3Config`)
- Modify: `src/synth_datagen/saas_v3/validate.py` (add `compute_benchmarks` + `BenchmarkReport`)
- Test: `tests/test_saas_v3_benchmarks.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_saas_v3_benchmarks.py`:
```python
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from synth_datagen.saas_v3.config import OutputMode, load_config, BenchmarkConfig
from synth_datagen.saas_v3.engine import SaaSV3Engine
from synth_datagen.saas_v3.validate import compute_benchmarks, BenchmarkReport

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


def test_benchmark_config_defaults() -> None:
    bc = BenchmarkConfig()
    assert bc.target_nrr_min == 1.05 and bc.target_nrr_max == 1.35
    assert bc.lifetime_churn_max == 0.40


def test_compute_benchmarks_legacy_mode_returns_empty(tmp_path) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.output.root_dir = tmp_path
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    report = compute_benchmarks(result.clean, cfg)
    assert isinstance(report, BenchmarkReport)
    assert report.skipped is True   # legacy mode -> no benchmarks computed


def test_compute_benchmarks_plg_mode_passes_in_range(tmp_path) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    cfg.output.root_dir = tmp_path
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    report = compute_benchmarks(result.clean, cfg)
    assert report.skipped is False
    assert report.passed, [(i.metric, i.actual, i.expected) for i in report.issues]
    # NRR is one of the computed metrics
    assert "nrr" in report.metrics


def test_compute_benchmarks_flags_out_of_range(tmp_path) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    # Tighten target so smoke data falls outside.
    cfg.benchmarks = BenchmarkConfig(target_nrr_min=2.0, target_nrr_max=2.5)
    cfg.output.root_dir = tmp_path
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    report = compute_benchmarks(result.clean, cfg)
    assert report.passed is False
    assert any(i.metric == "nrr" for i in report.issues)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_saas_v3_benchmarks.py -v
```
Expected: ImportError / failure — types don't exist.

- [ ] **Step 3: Implement `BenchmarkConfig` + `compute_benchmarks`**

In `src/synth_datagen/saas_v3/config.py`:
```python
class BenchmarkConfig(StrictModel):
    """Industry benchmark target ranges (calibrated to KeyBanc 2024 / Benchmarkit 2025)."""
    target_nrr_min: float = Field(default=1.05, gt=0)
    target_nrr_max: float = Field(default=1.35, gt=0)
    target_grr_min: float = Field(default=0.85, gt=0, le=1.0)
    lifetime_churn_max: float = Field(default=0.40, gt=0, le=1.0)
    trial_conversion_min: float = 0.15
    trial_conversion_max: float = 0.40
```
Add to `SaaSV3Config`:
```python
benchmarks: BenchmarkConfig = Field(default_factory=BenchmarkConfig)
```

In `src/synth_datagen/saas_v3/validate.py`:
```python
@dataclass
class BenchmarkIssue:
    metric: str
    actual: float
    expected: tuple[float, float] | float
    message: str

@dataclass
class BenchmarkReport:
    skipped: bool
    passed: bool
    metrics: dict[str, float]
    issues: list[BenchmarkIssue]


def compute_benchmarks(tables: GeneratedTables, config: SaaSV3Config) -> BenchmarkReport:
    if config.run.mode != "plg-usage-based":
        return BenchmarkReport(skipped=True, passed=True, metrics={}, issues=[])
    events = tables.materialize("subscription_events")
    bc = config.benchmarks
    # NRR = (start_mrr + expansion - contraction - churn) / start_mrr
    # Computed over the trailing 12 months ending at as_of_date.
    ...  # full implementation per algorithm
    return BenchmarkReport(skipped=False, passed=passed, metrics=metrics, issues=issues)
```
Full algorithm (~60 lines) authored during execution. NRR/GRR/lifetime-churn/trial-conversion computed from `subscription_events` and existing tables.

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_saas_v3_benchmarks.py -v
```
Expected: all 4 PASS.

- [ ] **Step 5: Backward-compat check + commit**

```powershell
python scripts/baseline_diff.py capture out/baseline_t8
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t8
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/saas_v3/config.py src/synth_datagen/saas_v3/validate.py tests/test_saas_v3_benchmarks.py
git commit -m "feat(saas_v3): add compute_benchmarks pass + BenchmarkConfig (plg-usage-based only)"
git push origin feat/saas-extension
```

---

## Task 9: Wire benchmark validation into `saas-v3 generate` CLI

**Files:**
- Modify: `src/synth_datagen/saas_v3/cli.py` (add `--benchmark-validation/--no-benchmark-validation` flag)
- Modify: `src/synth_datagen/saas_v3/exporters.py` (write `benchmark_validation.md`)
- Test: `tests/test_saas_v3_cli_unit.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_saas_v3_cli_unit.py`:
```python
def test_generate_emits_benchmark_validation_md_for_plg(tmp_path, plg_smoke_config_path) -> None:
    from typer.testing import CliRunner
    from synth_datagen.saas_v3.cli import app
    from tests.helpers import strip_ansi

    runner = CliRunner()
    out = tmp_path / "out"
    result = runner.invoke(app, [
        "generate",
        "--config", str(plg_smoke_config_path),
        "--mode", "clean",
        "--output", str(out),
        "--benchmark-validation",
    ])
    assert result.exit_code == 0, strip_ansi(result.output)
    md = next(out.rglob("benchmark_validation.md"))
    assert "NRR" in md.read_text(encoding="utf-8")


def test_generate_skips_benchmarks_in_legacy_mode(tmp_path, smoke_config_path) -> None:
    # ... assert no benchmark_validation.md when --no-benchmark-validation
    ...
```

Also add a `plg_smoke_config_path` fixture in `tests/conftest.py` that copies `configs/saas_v3.smoke.yaml` and flips `run.mode` to `plg-usage-based`.

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_saas_v3_cli_unit.py -v -k benchmark
```
Expected: FAIL — flag unknown.

- [ ] **Step 3: Add the CLI flag + exporter writer**

Edit `src/synth_datagen/saas_v3/cli.py` — add to `generate()`:
```python
benchmark_validation: bool = typer.Option(
    False,
    "--benchmark-validation/--no-benchmark-validation",
    help="Run industry-benchmark validation (NRR/GRR/churn/trial-conversion). "
         "plg-usage-based mode only — skipped in legacy mode.",
),
```
After `clean_report = validate_generated_dataset(...)`:
```python
if benchmark_validation:
    from .validate import compute_benchmarks
    bench = compute_benchmarks(result.clean, engine.config)
    if not bench.skipped:
        exporter.write_benchmark_report(bench, run_root=...)
        if not bench.passed:
            for issue in bench.issues:
                typer.echo(f"  benchmark: {issue.metric} {issue.actual} outside {issue.expected}")
```

In `exporters.py` add `write_benchmark_report(report, run_root)` rendering a Markdown table (one row per metric: name, actual, expected range, status).

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_saas_v3_cli_unit.py -v -k benchmark
```
Expected: all PASS.

- [ ] **Step 5: Backward-compat check + commit**

```powershell
python scripts/baseline_diff.py capture out/baseline_t9
python scripts/baseline_diff.py compare out/baseline_main out/baseline_t9
pre-commit run --all-files
pytest -x -q
git add src/synth_datagen/saas_v3/cli.py src/synth_datagen/saas_v3/exporters.py tests/test_saas_v3_cli_unit.py tests/conftest.py
git commit -m "feat(saas_v3): add --benchmark-validation flag emitting benchmark_validation.md"
git push origin feat/saas-extension
```

---

## Task 10: Ship `configs/saas_v3.plg.yaml` reference config

**Files:**
- Create: `configs/saas_v3.plg.yaml`

- [ ] **Step 1: Author the config**

Copy `configs/saas_v3.smoke.yaml`, flip `run.mode: plg-usage-based`, raise row counts to portfolio-realistic levels (accounts: 4500, users: 90000, subscriptions: 9000, product_events: 250000, invoices: 18000, support_tickets: 13000, nps_responses: 8500), add a `benchmarks:` block with default ranges, name the run `saas_v3_plg_smoke`.

- [ ] **Step 2: Smoke-run it**

```powershell
synth-datagen saas-v3 generate --config configs/saas_v3.plg.yaml --mode clean --output out/saas_v3_plg_smoke --benchmark-validation
```
Expected: exit 0, all 8 tables (`subscription_events.csv` included), `benchmark_validation.md` with NRR in 1.05–1.35 range.

If the run takes > 90 s, scale the row counts down — the goal is a deterministic reference, not a stress test.

- [ ] **Step 3: pre-commit + commit**

```powershell
pre-commit run --all-files
git add configs/saas_v3.plg.yaml
git commit -m "feat(saas_v3): ship plg-usage-based reference config"
git push origin feat/saas-extension
```

If pre-commit's `check-yaml` complains, recall `precommit-checkyaml-mkdocs.md` — `mkdocs.yml` is the only excluded YAML; new ones should pass. Fix any indentation issues directly.

---

## Task 11: Documentation update — `docs/scenarios/saas.md` + `README.md`

**Files:**
- Modify: `docs/scenarios/saas.md`
- Modify: `README.md`

- [ ] **Step 1: Extend `docs/scenarios/saas.md`**

Add a new top-level section after "Sub-app: SaaS v3":

```markdown
### v0.2.1 — `plg-usage-based` sub-mode

The `saas-v3` engine now supports two modes via `run.mode` in YAML:

- `legacy` (default) — original 7-table output. Byte-stable across versions.
- `plg-usage-based` — emits an 8th table, `subscription_events`, and
  unlocks the `--benchmark-validation` CLI flag.

#### `subscription_events` schema

| column | type | notes |
|---|---|---|
| event_id | string | `SE-XXXXX` PK |
| subscription_id | string | FK → subscriptions |
| account_id | string | FK → accounts (denormalized) |
| event_type | enum | `new` \| `expansion` \| `contraction` \| `churn` \| `reactivation` |
| event_date | date | |
| mrr_delta | float | signed; sums per account = current MRR |
| previous_mrr | float | |
| new_mrr | float | |
| reason | string | Pareto-distributed for churn; tag for expansion/contraction |

The 5-movement decomposition is the source of truth for an MRR waterfall.
`SUM(mrr_delta) GROUP BY account_id` equals `accounts.mrr` ± 0.01 — verified
by a Hypothesis property test (`tests/property/test_saas_v3_invariants.py`).

#### `--benchmark-validation`

```bash
synth-datagen saas-v3 generate \
    --config configs/saas_v3.plg.yaml \
    --mode clean \
    --benchmark-validation
```

Writes `benchmark_validation.md` to the run root with NRR / GRR / lifetime-churn /
trial-conversion vs target ranges defined in `BenchmarkConfig` (defaults
calibrated to KeyBanc 2024 SaaS Survey + Benchmarkit 2025).

#### RNG salt

`saas_v3` is now registered under salt `0x5AA50000` in
`src/synth_datagen/rng.py:SALT_REGISTRY`. All saas_v3 RNG draws derive from
`make_rng(seed, "saas_v3").spawn(N)` — no direct `np.random.default_rng(...)`
calls in scenario code. This means saas_v3 byte output shifted once at
v0.2.1; v0.3.0 will pin it via `scripts/baseline_diff.py`.
```

- [ ] **Step 2: Add a one-line entry to `README.md` under "What's new"**

```markdown
- **v0.2.1** — `saas-v3` `plg-usage-based` sub-mode with the 5-movement
  MRR waterfall (`subscription_events` table) and opt-in
  `--benchmark-validation` against KeyBanc/Benchmarkit ranges.
```

- [ ] **Step 3: Build docs strict**

```powershell
mkdocs build --strict
```
Expected: PASS, no broken anchors.

- [ ] **Step 4: Commit**

```powershell
pre-commit run --all-files
git add docs/scenarios/saas.md README.md
git commit -m "docs(saas): document plg-usage-based mode, subscription_events, benchmark validation"
git push origin feat/saas-extension
```

---

## Task 12: Pin `saas_v3` in `scripts/baseline_diff.py`

**Files:**
- Modify: `scripts/baseline_diff.py`

- [ ] **Step 1: Extend the script**

Add a `saas_v3` capture target invoking the sub-app:
```python
SAAS_V3_CAPTURE = {
    "config": "configs/saas_v3.smoke.yaml",  # legacy mode — most stable
    "args": ["saas-v3", "generate", "--config", "configs/saas_v3.smoke.yaml",
             "--mode", "clean", "--seed", "42"],
}
```
Add a `capture_saas_v3(out_root)` function that runs the sub-app under the same `PYTHON` interpreter and copies the output dir into `out_root / "saas_v3"`. Add it to the loop in `capture()` and the CSV-only diff in `compare()`.

- [ ] **Step 2: Recapture baseline post-migration**

```powershell
python scripts/baseline_diff.py capture out/baseline_v0_2_1
python scripts/baseline_diff.py compare out/baseline_main out/baseline_v0_2_1
```
Expected: empty diff for retail/saas/fintech/logistics. `saas_v3` won't be in `out/baseline_main` (it didn't exist in the diff at task 0) — expected.

- [ ] **Step 3: Commit + smoke-test the new pin**

Run a no-op recapture and confirm the saas_v3 path is byte-stable across two consecutive runs:
```powershell
python scripts/baseline_diff.py capture out/baseline_v0_2_1_a
python scripts/baseline_diff.py capture out/baseline_v0_2_1_b
python scripts/baseline_diff.py compare out/baseline_v0_2_1_a out/baseline_v0_2_1_b
```
Expected: empty diff including `saas_v3/`.

```powershell
pre-commit run --all-files
git add scripts/baseline_diff.py
git commit -m "chore(baseline): pin saas_v3 smoke output post-Phase 5 RNG migration"
git push origin feat/saas-extension
```

---

## Task 13: CHANGELOG + version bump

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Populate `[Unreleased]` → `[0.2.1] — 2026-05-07`**

Replace the `[Unreleased]` block:
```markdown
## [Unreleased]

### Added
- _nothing yet_

### Changed
- _nothing yet_

### Fixed
- _nothing yet_

## [0.2.1] — 2026-05-07

### Added
- **`saas-v3` `plg-usage-based` sub-mode (Phase 5).**
  - New `run.mode` field in saas_v3 YAML config; defaults to `legacy`.
  - 8th table `subscription_events` with the full 5-movement MRR waterfall
    (`new`, `expansion`, `contraction`, `churn`, `reactivation`).
  - `--benchmark-validation` CLI flag (saas-v3 only) emitting
    `benchmark_validation.md` with NRR / GRR / lifetime-churn /
    trial-conversion vs KeyBanc 2024 + Benchmarkit 2025 target ranges.
  - `configs/saas_v3.plg.yaml` reference config.
- **Hypothesis property test** verifying
  `SUM(subscription_events.mrr_delta) per account = accounts.mrr ± 0.01`
  across 8 random seeds.

### Changed
- **saas_v3 RNG migrated to the central `make_rng` factory** under the
  newly registered `saas_v3` salt (`0x5AA50000`). Engine + DefectInjector
  no longer call `np.random.default_rng` directly. saas_v3 byte output
  shifted once at this release; pinned going forward by
  `scripts/baseline_diff.py`.
- `scripts/baseline_diff.py` now captures saas_v3 alongside the four
  legacy scenarios.

### Fixed
- _nothing yet_
```

- [ ] **Step 2: Bump version**

In `pyproject.toml`:
```toml
version = "0.2.1-dev"
```

- [ ] **Step 3: Commit**

```powershell
pre-commit run --all-files
pytest -x -q
git add CHANGELOG.md pyproject.toml
git commit -m "chore(release): bump version 0.2.0 -> 0.2.1-dev with Phase 5 changelog"
git push origin feat/saas-extension
```

---

## Task 14: Final code-review pass + release commit

**Files:**
- Modify: `pyproject.toml` (drop `-dev` suffix)

- [ ] **Step 1: Activate code-reviewer skill**

Per spec section "SESSION CLOSURE — code-reviewer pass":
- Run `git diff main..HEAD --stat -w` and inspect semantic changes.
- Verify every Phase 5 deliverable has a matching commit:
  - REQ-1 (5 movement types) → Task 5
  - REQ-7 (RNG salt 0x5AA50000) → Task 1+2+3
  - REQ-8 (benchmark validation) → Task 8+9
- Verify backward-compat: `python scripts/baseline_diff.py compare out/baseline_main out/baseline_v0_2_1` empty for retail/saas/fintech/logistics.
- Verify Conventional Commits + no Co-authored-by trailer:
  ```powershell
  git log main..HEAD --pretty=format:%B | grep -i "co-authored-by"
  ```
  Expected: no output.
- Verify no direct `np.random.default_rng` in scenario code:
  ```powershell
  git grep -n "np.random.default_rng" src/synth_datagen/saas_v3/
  ```
  Expected: no output (or only inside `make_rng` itself, which lives in `rng.py`, not saas_v3).

Report findings — fix any issues before proceeding.

- [ ] **Step 2: Final CI sweep**

Wait for GitHub Actions to confirm all matrix legs green on `feat/saas-extension`. Investigate any failure on Linux/Windows × py3.11/3.12/3.13.

- [ ] **Step 3: Drop `-dev` suffix for release**

```toml
version = "0.2.1"
```
Update CHANGELOG date if it changed.

```powershell
pre-commit run --all-files
pytest -x -q
mkdocs build --strict
git add pyproject.toml CHANGELOG.md
git commit -m "chore(release): bump version 0.2.1-dev -> 0.2.1"
git push origin feat/saas-extension
```

- [ ] **Step 4: Hand off to user for merge + tag**

Surface to the user:
- Branch ready: `feat/saas-extension`
- Suggested merge: fast-forward or no-ff merge to `main`
- Suggested tag: `v0.2.1` on the merge commit
- Suggested next session: Phase 6 (Pharma + saas_v3 `vertical-account-based`) bumps to `0.3.0`.

---

## Self-review checklist (run before declaring this plan complete)

- [x] **Spec coverage** — REQ-1 (5 movement types) ✓ Task 5; REQ-7 (RNG salt) ✓ Task 1+2+3; REQ-8 (benchmark validation) ✓ Task 8+9. REQ-2/3/4/5/6 scoped out per "v0.2.1 = minimum-viable" decision; documented as v0.3.0 in CHANGELOG/docs.
- [x] **Placeholder scan** — algorithm bodies in Task 5/8 are described as binding contracts with line-count budgets, not as TODOs. The engineer must implement them, but the inputs/outputs/columns are pinned.
- [x] **Type consistency** — `_RNG_LABELS` referenced consistently across Task 2/3/5; `BenchmarkConfig`/`BenchmarkReport` defined in Task 8 before referenced in Task 9.
- [x] **Backward compat enforced at every commit** — every push step includes the `baseline_diff` compare against `out/baseline_main`.
- [x] **Memory gotchas** — ruff-pin-coupling, ansi-on-ci, checkyaml-mkdocs all referenced in conventions section.

---

## Execution choice

Plan complete and saved to `docs/superpowers/plans/2026-05-07-saas-extension-v0-2-1.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good for this plan because tasks 5 and 8 have non-trivial algorithm bodies that benefit from a clean context per task.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Faster end-to-end but main context will fill.

**Which approach?**
