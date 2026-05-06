## ROLE
You are a Python testing specialist with expertise in:
- pytest fixtures, parametrization, and markers
- Hypothesis property-based testing
- Coverage analysis and gap closure
- Integration testing with realistic scenarios
- Benchmark validation (statistical assertions)

## CONTEXT
Phase 2 of the synth-datagen refactor is complete. The codebase is clean, type-safe, and structured. Now we harden the test suite to publication quality.

## METHODOLOGY
Use Superpowers `test-driven-development` and `verification-before-completion` skills.
Use ECC `python-testing` skill for pytest patterns.

## TASK

### Step 1: Coverage gap analysis
```bash
pytest --cov=src/synth_datagen --cov-report=term-missing --cov-report=html
```
Identify:
- Modules with < 80% coverage (priority: bring to 80%)
- Untested branches in scenario logic
- Untested error paths

### Step 2: Add property-based tests with Hypothesis

For each scenario, add property tests in `tests/property/test_invariants.py`:

```python
from hypothesis import given, strategies as st, settings
from synth_datagen.scenarios import retail

@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=50, deadline=10000)
def test_retail_reproducibility_property(seed):
    """Same seed must produce identical output, for any seed."""
    output_1 = retail.generate(seed=seed, scale=100)
    output_2 = retail.generate(seed=seed, scale=100)
    assert output_1.equals(output_2)

@given(seed=st.integers(min_value=0, max_value=2**32 - 1),
       scale=st.integers(min_value=100, max_value=10000))
def test_retail_margin_invariants(seed, scale):
    """Margin must always be in plausible range."""
    data = retail.generate(seed=seed, scale=scale)
    overall_margin = compute_margin(data)
    assert 0.40 < overall_margin < 0.70, f"Implausible margin: {overall_margin}"

@given(seed1=st.integers(), seed2=st.integers())
def test_seeds_produce_different_data(seed1, seed2):
    """Different seeds must produce different output."""
    if seed1 == seed2:
        return  # skip
    out1 = retail.generate(seed=seed1, scale=100)
    out2 = retail.generate(seed=seed2, scale=100)
    assert not out1.equals(out2)
```

Cover these invariants per scenario:
- **Reproducibility:** same seed → identical output
- **Stream isolation:** changing one config doesn't affect unrelated fields
- **Schema stability:** column names and types are deterministic
- **Statistical bounds:** distributions stay in plausible ranges
- **Quality injection:** dirty mode produces N% errors ± tolerance
- **Foreign key integrity:** all FK references resolve

### Step 3: Add benchmark validation tests

For each scenario, add `tests/scenarios/test_<scenario>_benchmarks.py`:

```python
def test_saas_nrr_achievable():
    """SaaS scenario must produce NRR > 100% for at least one segment."""
    data = saas.generate(seed=42, scale=4500, sub_mode='plg-usage-based')
    nrr_by_segment = compute_nrr_by_segment(data)
    assert nrr_by_segment['Enterprise'] > 1.10, f"Got {nrr_by_segment['Enterprise']}"
    assert any(v > 1.10 for v in nrr_by_segment.values())

def test_saas_inverse_pyramid_churn():
    """Smaller customers should churn more (real SaaS pattern)."""
    data = saas.generate(seed=42, scale=4500)
    churn = compute_monthly_churn_by_plan(data)
    assert churn['Free'] > churn['Pro']
    assert churn['Pro'] > churn['Team']
    assert churn['Team'] > churn['Enterprise']

def test_saas_all_five_movement_types_present():
    """MRR waterfall requires all 5 movement types."""
    data = saas.generate(seed=42, scale=4500)
    types = set(data['subscription_events']['event_type'].unique())
    assert {'new', 'expansion', 'contraction', 'churn', 'reactivation'}.issubset(types)

def test_retail_margin_spread_by_segment():
    """RFM segments should produce 45-65% margin spread."""
    data = retail.generate(seed=42, scale=10000, discount_variation=True)
    margins = compute_margin_by_rfm_quintile(data)
    assert margins['top_quintile'] > 0.60
    assert margins['bottom_quintile'] < 0.52
```

### Step 4: Integration tests for CLI

Add `tests/test_cli_integration.py`:

```python
import subprocess
import json
from pathlib import Path

def test_cli_retail_end_to_end(tmp_path):
    """End-to-end CLI run produces expected output files."""
    result = subprocess.run([
        'synth-datagen', 'retail',
        '--seed', '42',
        '--scale', '1000',
        '--output-dir', str(tmp_path),
        '--output-format', 'csv',
    ], capture_output=True, text=True)
    assert result.returncode == 0

    # Verify expected files
    assert (tmp_path / 'fact_orders.csv').exists()
    assert (tmp_path / 'dim_customers.csv').exists()
    assert (tmp_path / 'metadata.json').exists()
    assert (tmp_path / 'data_dictionary.md').exists()

    # Verify metadata
    metadata = json.loads((tmp_path / 'metadata.json').read_text())
    assert metadata['seed'] == 42
    assert 'rng_state_hash' in metadata
```

### Step 5: Performance regression tests

Add `tests/test_performance.py`:

```python
import time

def test_retail_10k_orders_under_5s():
    """Generation performance must not regress."""
    start = time.perf_counter()
    retail.generate(seed=42, scale=10000)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"Generation took {elapsed:.2f}s (budget: 5s)"
```

### Step 6: CI configuration

Create `.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12', '3.13']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[test]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy src/
      - run: bandit -r src/
      - run: pytest --cov=src/synth_datagen --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4
```

## DELIVERABLE

By end of Phase 3:
- [ ] Coverage >= 85% for all `src/synth_datagen/` modules
- [ ] At least 5 property-based tests per scenario using Hypothesis
- [ ] Benchmark validation tests for every scenario
- [ ] CLI integration tests
- [ ] Performance regression tests with budgets
- [ ] CI workflow runs on push/PR for Python 3.11, 3.12, 3.13
- [ ] All tests pass, no flaky tests (run pytest 5 times in a row)

## SUCCESS CRITERIA
- CI workflow passes on a fresh PR
- Coverage report shows specific gaps with justifications (not just numbers)
- A single `pytest` invocation runs everything in < 60 seconds
- Property tests have caught at least one previously-unknown edge case (document it in CHANGELOG)

---

## Session-specific priority order (operator override)

The operator has set the following execution order for this session, which
takes precedence over the canonical step order in TASK above when they conflict.
Reproduction details for the leap-day bug live in `audit_report.md` L495–510.

1. **CRLF/LF cleanup commit** — add `.gitattributes` (LF normalization) and
   run `ruff format` over the tree. Single commit, message:
   `chore: enforce LF line endings and ruff format pass (P1-10)`.
   Must run before any test work so subsequent diffs stay readable.
2. **Feb-29 leap-day fintech crash** — TDD: failing test first that runs
   fintech with seed=42 across year boundaries including 2024 and 2028,
   then fix the default-scale crash, then make the test pass.
3. **Hypothesis property tests** — 5+ per scenario for retail, saas, fintech,
   logistics, kupferkanne_rfm. Use `@settings(database=None)` for determinism.
4. **Reproducibility tests for fintech and logistics** (P2-7).
5. **CSV roundtrip / byte-equality tests** (P2-8).
6. **Slow-test trim** to bring pytest under 60s (P1-12). Profile with
   `pytest-durations`, parametrize down or split into fast/slow markers.
7. **Coverage hardening** on lowest-coverage modules to ≥85%:
   parquet_exporter (27%), saas_v3/cli (41%), sql_exporter (72%),
   schema_builder (74%).
8. **CI workflow** `.github/workflows/ci.yml`: matrix Python 3.11/3.12/3.13,
   pytest + ruff check + ruff format --check + mypy on every push and PR.
9. **pre-commit config** `.pre-commit-config.yaml`: ruff, mypy,
   end-of-file-fixer, trailing-whitespace.

## Session-specific constraints

- TDD enforced (Superpowers skill).
- Backward compat is a hard line: baseline diff retail/saas/fintech/logistics
  with prior seeds must stay empty across every commit.
- Conventional Commits, no `Co-Authored-By` trailer.
- Coverage ≥85% on `src/synth_datagen/` (currently 91%, must not regress).
- pytest must pass 5x in a row (no flaky tests).
- Single pytest run < 60s after slow-test trim.
- Push to `origin feat/test-hardening` after each commit (backup).
- 3 failed attempts on the same issue → STOP, invoke brainstorming skill.
- At session end: `code-reviewer` agent reviews diff against main; report
  any issues before declaring done.
