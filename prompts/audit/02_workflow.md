# synth-datagen Audit & Refactor Workflow
## A 4-phase Coding Agent battle plan to take the engine from "works" to "portfolio-grade"

> **Goal:** Audit your existing `synth-datagen` Python codebase for correctness, code quality, structural issues, and bugs — then refactor to professional-grade in the shortest possible time. Output: a repo you'd be proud to publish on GitHub as the engine behind your portfolio.
>
> **Timeline:** 1-2 working days of focused agent work + 2-3 hours of your review time, spread over a week.
>
> **Coding agent:** Claude Code (recommended) or OpenAI Codex. Both work with the skills below.
>
> **Skill stack:** Superpowers (`obra/superpowers`) for methodology + ECC (`affaan-m/everything-claude-code`) for security/Python patterns.

---

## 0. Prerequisites — install before starting

Run these once. Total setup time: ~10 minutes.

### Install strategy: Superpowers full, ECC selective

| Library | Strategy | Reason |
|---------|----------|--------|
| **Superpowers (`obra/superpowers`)** | Install ALL (14 skills) | Coherent methodology — skills work together, cherry-picking breaks workflow |
| **ECC (`affaan-m/everything-claude-code`)** | Install SELECTIVE (4 skills only) | 50+ skills available, most irrelevant to this project. Avoid context bloat. |

### Step 1: Superpowers (full install)

```bash
# In Claude Code:
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

This gives you all 14 skills (`brainstorming`, `systematic-debugging`, `test-driven-development`, `subagent-driven-development`, `verification-before-completion`, `writing-plans`, `using-git-worktrees`, `code-reviewer` agent, etc.) plus the session-start hook that auto-activates skills based on task type.

### Step 2: ECC (selective — only 4 skills)

```bash
# In Claude Code:
/plugin marketplace add affaan-m/everything-claude-code

# Option A — selective install via flag (if supported in your ECC version):
/plugin install everything-claude-code@everything-claude-code --skills python-patterns,python-testing,search-first,security-scan

# Option B — manual selective copy (always works):
git clone https://github.com/affaan-m/everything-claude-code /tmp/ecc
mkdir -p ~/.claude/skills/
cp -r /tmp/ecc/skills/python-patterns ~/.claude/skills/
cp -r /tmp/ecc/skills/python-testing ~/.claude/skills/
cp -r /tmp/ecc/skills/search-first ~/.claude/skills/
cp -r /tmp/ecc/skills/security-scan ~/.claude/skills/
```

⚠️ **CRITICAL warning from ECC v2.0.0-rc.1 docs:** If you install ECC via `/plugin install`, do NOT also run `./install.sh --profile full`. That copies all skills to user directories and creates duplicates with duplicate runtime behavior. Pick ONE install method and stick with it.

#### Why these 4 ECC skills specifically

| Skill | Used in Phase | Why essential |
|-------|--------------|---------------|
| `python-patterns` | Phase 2 (refactor) | Type hints, dataclass patterns, Pydantic v2 idioms |
| `python-testing` | Phase 3 (tests) | pytest fixtures, hypothesis property tests, coverage analysis |
| `search-first` | Phase 1 (audit) | Forces research before any changes — critical for audit phase |
| `security-scan` | Phase 1, 4 (security) | Scans for credentials, injection risks, unsafe patterns |

#### What you DON'T need from ECC (and why)

`react-patterns`, `typescript-patterns` — no React/TypeScript in this project. `database-skills` — generating CSV, not managing databases. `api-design` — no REST API, CLI only. `deployment-skills`, `mcp-skills`, `frontend-skills`, `kubernetes-skills` — none apply to this scope.

### Step 3: Verify install

```bash
# In Claude Code:
/plugin list
# Should show: superpowers, everything-claude-code

# In a fresh session, verify skills are loaded:
"List all available skills currently loaded in this session"
```

### Step 4: Optional baseline security scan

```bash
cd X:\Python\projects\synth-datagen
npx ecc-security-scan scan --no-install
```

Run this once before Phase 1. If it finds P0 (e.g., hardcoded API key in git history), fix BEFORE starting the audit workflow.

### Context cost analysis

After selective install, you have:
- Superpowers metadata (14 skills): ~2000-3000 tokens always-on
- ECC metadata (4 skills): ~600-1000 tokens always-on
- Active skills (loaded on demand): typically 1-3 skills at a time, ~1500-5000 tokens when active

**Total context overhead: ~3500-9000 tokens.** Acceptable for both Claude Code Pro (200K window) and OpenAI Codex (128K window).

After install, the agent automatically loads relevant skills based on task type via the session-start hook. You don't need to manually invoke them most of the time — that's the point of the skills system.

---

## Why this skill stack?

The two skill libraries are complementary, not competing:

| Skill source | What it gives you | When it triggers |
|--------------|-------------------|------------------|
| **Superpowers** | Methodology: brainstorming → planning → TDD → systematic debugging → verification | Activates automatically on any non-trivial coding task |
| **ECC** | Domain: Python patterns, security scanning, research-first development, Codex/Codeguard hooks | Activates on Python work, security audits |

**Critical Superpowers skills for this project:**
- `brainstorming` — refuses to write code until requirements are clarified
- `systematic-debugging` — 4-phase root cause process (no random fixes)
- `test-driven-development` — red/green/refactor enforced
- `subagent-driven-development` — fast iteration with built-in code review
- `writing-plans` — breaks features into 2-5 minute tasks
- `verification-before-completion` — concrete evidence of success required

**Critical ECC skills for this project:**
- `python-patterns` — Python idioms, type hints, dataclass patterns
- `python-testing` — pytest, hypothesis, coverage
- `search-first` — research existing code before changing it
- `security-scan` — security scan for credentials, injection risks

---

## Workflow overview: 4 phases

```
PHASE 1 (1-2h)        PHASE 2 (4-6h)        PHASE 3 (4-6h)        PHASE 4 (2-3h)
┌────────────┐         ┌────────────┐         ┌────────────┐         ┌────────────┐
│   AUDIT    │  ──→    │  REFACTOR  │  ──→    │   TESTS &  │  ──→    │ DOCUMENT & │
│            │         │            │         │ VALIDATION │         │  PUBLISH   │
│ Read-only  │         │ Surgical   │         │ Property + │         │ README,    │
│ analysis   │         │ changes    │         │ integration│         │ docs site, │
│ + report   │         │ per audit  │         │ tests      │         │ release    │
└────────────┘         └────────────┘         └────────────┘         └────────────┘
   Day 1 AM            Day 1 PM + Day 2        Day 2-3              Day 3
```

Each phase has a dedicated agent prompt. Run them in order. Don't skip Phase 1 — the audit drives everything else.

---

## PHASE 1 — Audit (read-only, no code changes)

**Goal:** Generate a comprehensive audit report of the current state of `synth-datagen`. The agent reads everything, runs static analysis tools, and produces a prioritized findings report. **No code is modified in this phase.**

**Estimated time:** 1-2 hours of agent work.

### Prompt 1: Audit

```markdown
## ROLE
You are a senior Python code reviewer and refactoring specialist with deep expertise in:
- Python 3.11+ idioms (type hints, dataclasses, Pydantic v2, Protocol types)
- Synthetic data generation architecture
- Statistical correctness (RNG isolation, distribution parametrization)
- Code quality tooling (ruff, mypy, bandit, radon, pytest)
- Repository hygiene (PEP 621, src layout, conventional commits)

## CONTEXT
You are auditing a private Python repository called `synth-datagen` (sometimes named `synthetic_data` in older docs). This is a CLI tool that generates synthetic business datasets for portfolio data analytics projects (retail, SaaS, fintech, logistics scenarios). It uses Typer for CLI, Pydantic for config, and emits CSVs with auto-generated documentation.

Key architectural patterns the user has confirmed exist:
- `--seed` flag with isolated RNG streams: `discount_rng = numpy.random.default_rng(seed=base_seed ^ 0xD15C0UNT)`
- Beta distribution parametrization for segment-aware propensities
- `--discount-variation` CLI flag pattern
- Configurable data quality injection (clean / medium / messy)
- Auto-documentation output

This repo will be made public as part of the user's data analyst portfolio. It must look like senior-level code, not bootcamp-level code.

## TASK
Conduct a complete read-only audit. DO NOT MODIFY ANY CODE in this phase. Your output is a single comprehensive audit report.

## METHODOLOGY (use Superpowers skills)
Use `search-first` skill: research the codebase before forming opinions.
Use `systematic-debugging` skill if you encounter unclear behavior — investigate, don't guess.

## STEP 1: REPOSITORY RECONNAISSANCE
Run these commands and document findings:

```bash
# Repository structure
tree -L 3 -I '__pycache__|*.egg-info|.git|node_modules|dist|build'
find . -type f -name "*.py" | head -50
wc -l $(find . -type f -name "*.py")

# Configuration files
cat pyproject.toml setup.py setup.cfg .pre-commit-config.yaml 2>/dev/null
cat .python-version Pipfile poetry.lock requirements*.txt 2>/dev/null

# Documentation state
ls -la README.md docs/ CHANGELOG.md LICENSE 2>/dev/null
cat README.md | head -100

# Test infrastructure
find . -path ./node_modules -prune -o -name "test_*.py" -print -o -name "*_test.py" -print
find . -name "pytest.ini" -o -name "tox.ini" -o -name "conftest.py"

# Git state
git log --oneline -20
git status
git branch -a
```

## STEP 2: STATIC ANALYSIS (read-only, run from temp venv)
Install tools in a temporary venv (do not modify project deps):
```bash
python -m venv /tmp/synth-audit-venv
source /tmp/synth-audit-venv/bin/activate
pip install ruff mypy bandit radon vulture pyright pip-audit
```

Run analysis:
```bash
ruff check . --statistics
ruff format --check .
mypy . --ignore-missing-imports --no-strict-optional 2>&1 | head -100
bandit -r . -f json | head -200
radon cc . -a -nb     # complexity
radon mi .            # maintainability index
vulture . --min-confidence 80   # dead code
pip-audit              # dependency vulnerabilities
```

## STEP 3: ARCHITECTURE REVIEW
Document for each scenario (retail, saas, fintech, logistics):
- Entry point file
- Lines of code
- Number of public functions/classes
- Test coverage (if measurable)
- RNG stream isolation: is it consistent?
- CLI flag patterns: are they uniform across scenarios?
- Output schema: is it documented?

Look specifically for:
- Code duplication between scenarios (DRY violations)
- Magic numbers without source comments
- Functions > 50 lines (refactoring candidates)
- Cyclomatic complexity > 10
- Missing type hints
- Inconsistent naming (snake_case vs camelCase)
- TODO/FIXME/HACK comments
- print() statements where logging should be used

## STEP 4: STATISTICAL CORRECTNESS REVIEW
This is the most important section. Verify:

**RNG isolation (REQ from prior conversations):**
- [ ] Each generation concern uses isolated RNG via XOR salt or `.spawn()`
- [ ] `--seed` flag truly produces deterministic output (write a test plan)
- [ ] Adding new logic doesn't shift existing RNG streams (bit-for-bit compatibility)

**Distribution correctness:**
- [ ] Beta distributions: α, β parametrization sourced from documentation
- [ ] Log-normal: mean, sigma cited from benchmarks
- [ ] Pareto: alpha parameter justified
- [ ] Uniform distributions used only where appropriate (mostly: never)

**Industry plausibility:**
- [ ] Margin spreads in retail data (e.g., 45-65% by segment)
- [ ] Discount propensity bands follow real-world patterns
- [ ] No "synthetic data fingerprints" (uniform churn rates, flat distributions)

## STEP 5: SECURITY REVIEW
Run:
```bash
npx ecc-security-scan scan --no-install
```

Check for:
- [ ] Hardcoded secrets, API keys, credentials in code or git history
- [ ] `eval()`, `exec()`, `pickle.load()` usage
- [ ] SQL injection vectors in any DDL output
- [ ] Path traversal in file output paths
- [ ] Unsafe YAML loading
- [ ] Subprocess calls with shell=True

## STEP 6: DOCUMENTATION DEBT
Document gaps:
- [ ] Missing docstrings on public functions
- [ ] No README.md or sparse README
- [ ] No CONTRIBUTING.md
- [ ] No CHANGELOG.md
- [ ] No examples directory
- [ ] No published data dictionary format documentation
- [ ] Type hints missing on public APIs

## STEP 7: REPRODUCIBILITY TEST
Run twice with same seed, diff the output:
```bash
synth-datagen retail --seed 42 --output-dir /tmp/run1
synth-datagen retail --seed 42 --output-dir /tmp/run2
diff -r /tmp/run1 /tmp/run2
# Should be empty diff. If not — flag as P0 bug.
```

Repeat for every scenario (saas, fintech, logistics).

## DELIVERABLE: AUDIT REPORT

Write to `audit_report.md` in the repo root. Structure:

```markdown
# synth-datagen Audit Report
Date: [DATE]
Auditor: Claude Code (Phase 1 audit)
Repo state: [git rev-parse HEAD]

## Executive Summary
- Overall code health score: X/10
- P0 issues found: N (block release)
- P1 issues found: N (must fix before public release)
- P2 issues found: N (nice to have)
- Lines of code: N
- Test coverage: X%
- Critical recommendations: [3 bullet points]

## Findings by Severity

### P0 — Critical (block release)
[List with file:line references and reproduction steps]

### P1 — High (fix before public release)
[List with file:line references]

### P2 — Medium (post-release improvements)
[List with file:line references]

### P3 — Low (nice to have)
[List with file:line references]

## Statistical Correctness Findings
[RNG, distributions, plausibility]

## Architecture Findings
[Duplication, complexity, structure]

## Security Findings
[From bandit + security-scan]

## Documentation Gaps
[What's missing]

## Recommended Refactor Plan
Ordered list of changes that maximizes value-per-hour:
1. [...]
2. [...]
...

## Files Touched In Phase 2 (Preview)
[List of files that will need modification]
```

## CONSTRAINTS
- DO NOT modify any code in this phase
- DO NOT install dependencies into the project venv (use /tmp venv)
- DO NOT commit anything
- DO output a single audit_report.md file
- DO stop and report any P0 issues immediately

## SUCCESS CRITERIA
The audit report is complete when:
- Every Python file has been read (or explicitly skipped with reason)
- All static analysis tools have been run with output captured
- Reproducibility test has been executed for every scenario
- The report is structured for actionable Phase 2 work
- The user can decide GO/NO-GO on Phase 2 based on this report alone
```

---

### After Phase 1: human review checkpoint

Read `audit_report.md`. Spend 30 minutes reviewing. Decide:

- **GO:** Audit looks reasonable, P0 count is manageable → proceed to Phase 2
- **NO-GO:** Major P0 issues require thinking → spend a day deciding architecture direction before Phase 2

Tell the agent which findings to address in Phase 2 (you don't have to address all of them).

---

## PHASE 2 — Surgical Refactor

**Goal:** Address audit findings in priority order. Each change is small, tested, and committed. Use TDD enforced by Superpowers.

**Estimated time:** 4-6 hours of agent work, broken into 6-10 small commits.

### Prompt 2: Refactor

```markdown
## ROLE
You are a Python refactoring specialist executing a structured refactor based on a completed audit. You work in surgical, test-first increments — never big-bang changes.

## CONTEXT
The audit phase produced `audit_report.md`. The user has reviewed it and approved the following findings for Phase 2:

[USER PASTES THE LIST OF FINDINGS TO ADDRESS HERE]

You are working on the same repo as Phase 1. Use Superpowers methodology throughout — this is non-negotiable.

## METHODOLOGY (use Superpowers skills, automatically loaded)
- `brainstorming` — for any finding that's ambiguous, ask clarifying questions BEFORE coding
- `writing-plans` — write a plan before each finding fix
- `test-driven-development` — write a failing test first, then the fix
- `subagent-driven-development` — for findings that touch 3+ files, dispatch a subagent
- `using-git-worktrees` — create a worktree for isolated experimentation
- `verification-before-completion` — concrete evidence each fix works

## TASK
Execute the approved findings list in priority order: P0 first, then P1, then P2.

For each finding:
1. Read the finding from audit_report.md
2. If unclear, invoke brainstorming skill (don't guess)
3. Write a plan in `tasks/plan_<finding_id>.md`
4. Write the failing test that captures the bug or missing behavior
5. Implement the fix
6. Verify the test passes
7. Run the full test suite to verify no regressions
8. Commit with conventional commit format: `fix:`, `refactor:`, `test:`, `docs:`
9. Move to the next finding

## CRITICAL CONSTRAINTS

### Backward compatibility (HARD requirement)
All existing scenarios (retail, saas, fintech, logistics) must continue to produce IDENTICAL output for a given seed after refactor. This is non-negotiable because the user's existing portfolio projects (Kupferkanne) depend on stable output.

Before any change to a generator:
1. Run the scenario with seed=42, save output as baseline_before/
2. Make the change
3. Run with seed=42 again, save as baseline_after/
4. Diff baseline_before/ vs baseline_after/
5. If diff is non-empty: STOP. Investigate. Either:
   a. The change broke determinism (bug — fix)
   b. The change is intentional behavior change (document and version-bump)

### RNG stream isolation (HARD requirement)
Any new RNG stream MUST use the XOR salt pattern or `.spawn()` to avoid affecting existing streams:
```python
new_concern_rng = numpy.random.default_rng(seed=base_seed ^ 0xNEWCONCERN)
# OR
new_concern_rng = master_rng.spawn(1)[0]
```
Never reuse an existing RNG for a new concern. Never use the global numpy random state.

### Test before fix (TDD enforced)
Every fix must have a test that:
1. Failed before the fix (proven by running it on the previous commit)
2. Passes after the fix (proven by running it on the current commit)

Skip this discipline → revert the commit. No exceptions.

### Conventional commits
Use the prefix that matches the change:
- `fix:` for bug fixes
- `refactor:` for non-functional changes (renames, restructures)
- `feat:` for new functionality
- `test:` for adding tests
- `docs:` for documentation only
- `chore:` for tooling, deps, configs

## ARCHITECTURE TARGETS

By end of Phase 2, the repo should have:

### Clean structure (src layout)
```
synth-datagen/
├── pyproject.toml          (PEP 621, single source of truth for metadata)
├── README.md               (with quickstart)
├── CHANGELOG.md
├── LICENSE
├── .pre-commit-config.yaml (ruff + mypy + bandit hooks)
├── .github/workflows/      (CI: tests + linting)
├── src/synth_datagen/      (NOT a flat package — src layout)
│   ├── __init__.py         (version + __all__)
│   ├── cli.py              (Typer entry point)
│   ├── config.py           (Pydantic models)
│   ├── rng.py              (RNG stream factory — single source of truth)
│   ├── distributions.py    (Beta/Pareto/lognormal helpers with sources)
│   ├── quality.py          (data quality injection — shared across scenarios)
│   ├── docs.py             (auto-doc generation)
│   ├── scenarios/
│   │   ├── __init__.py
│   │   ├── _base.py        (Scenario protocol/base class)
│   │   ├── retail.py
│   │   ├── saas.py
│   │   ├── fintech.py
│   │   └── logistics.py
│   └── benchmarks/         (industry benchmark constants with sources)
│       ├── retail.py
│       ├── saas.py
│       └── ...
├── tests/
│   ├── conftest.py
│   ├── test_rng.py
│   ├── test_distributions.py
│   ├── test_reproducibility.py     ← P0 critical
│   ├── test_quality_injection.py
│   ├── scenarios/
│   │   ├── test_retail.py
│   │   ├── test_saas.py
│   │   └── ...
│   └── property/                    ← hypothesis-based property tests
│       └── test_invariants.py
└── examples/
    ├── retail_quickstart.py
    ├── saas_promptforge.py
    └── fintech_demo.py
```

### Code quality gates (enforced by pre-commit)
- ruff: 0 warnings on `--select ALL --ignore D` (or your chosen subset)
- mypy: 0 errors on `--strict` (achievable for new code; legacy can use `# type: ignore[reason]`)
- bandit: 0 high-severity findings
- pytest: 100% pass rate
- coverage: >= 80% for `src/synth_datagen/`

### Type safety
- All public APIs fully type-hinted
- Use `Protocol` types for scenario interface (not abstract base class — more Pythonic)
- Pydantic v2 for all configuration objects
- `from __future__ import annotations` at top of every module

## DELIVERABLE

After each finding fixed, append to `tasks/refactor_log.md`:
```markdown
## [DATE TIME] Finding #N: [Title]
- Files changed: [list]
- Tests added: [list]
- Lines added/removed: +X / -Y
- Backward compat verified: yes (baseline diff empty)
- Commit: [git hash]
```

After all findings addressed, write final summary in `audit_report.md`:
```markdown
## Phase 2 Resolution
Total findings addressed: N of M
P0 resolved: X/X
P1 resolved: X/X
Deferred to Phase 3: [list]
Test count before: X, after: Y
Coverage before: X%, after: Y%
```

## STOPPING CONDITIONS

Stop and ask the user:
- A finding's fix would break backward compatibility (need user decision on version bump)
- An ambiguous finding requires architectural direction
- Tests start failing in unexpected ways (use systematic-debugging skill)
- 3+ failed fix attempts on the same finding (architectural review needed)
- The refactor scope is expanding beyond the original audit list

## SUCCESS CRITERIA
Phase 2 is complete when:
- All approved findings have a "resolved" entry in refactor_log.md
- Every commit passes pre-commit hooks
- Every commit follows conventional commit format
- pytest reports 100% pass + coverage >= 80%
- Diff against baseline (per scenario, seed=42) is empty
- The repo can be cloned and `pytest` works on first try
```

---

## PHASE 3 — Tests & Validation

**Goal:** Add property-based tests, integration tests, and benchmark validation. This is what separates "code that works" from "code you'd publish."

**Estimated time:** 4-6 hours of agent work.

### Prompt 3: Test hardening

```markdown
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
```

---

## PHASE 4 — Documentation & Publication Prep

**Goal:** Make the repo presentable. This is portfolio polish.

**Estimated time:** 2-3 hours of agent work.

### Prompt 4: Documentation

```markdown
## ROLE
You are a technical writer specializing in open-source Python project documentation. You write README files that make engineers want to clone the repo, and docs sites that make them stay.

## CONTEXT
synth-datagen is now refactored, tested, and ready to publish. Your job is to make it presentable. The repo will be linked from the user's portfolio (Kupferkanne, SaaS Dashboard projects) and will be a senior-level signal in interviews.

## METHODOLOGY
Use Superpowers `verification-before-completion` to verify every code example actually runs.

## TASK

### Step 1: README.md (the most important file)

Structure (use this exact order):

```markdown
# synth-datagen

> One-line tagline emphasizing the unique value (not "synthetic data tool" — too generic)

[![CI](badge)](link) [![PyPI](badge)](link) [![Python](badge)](link) [![License](badge)](link)

**Tagline paragraph: 2-3 sentences. What it does, who it's for, what makes it different.**

## Quickstart

```bash
pip install synth-datagen
synth-datagen retail --seed 42 --scale 10000 --output-dir ./data
```

That's it. You now have 10K realistic e-commerce orders with referential integrity, segment-aware margin patterns, and intentional data quality issues for ETL practice.

## Why this exists

[2-3 paragraphs explaining the gap this fills. What's wrong with Faker for business datasets? Why not just download Kaggle data?]

## Features

- Multi-scenario: retail, SaaS, fintech, logistics
- Multi-table datasets with foreign key integrity
- Configurable data quality injection (clean / medium / messy)
- Reproducible: same seed = identical output
- Industry-benchmark calibrated distributions (cite sources)
- Auto-generated documentation (data dictionary, ERD, lineage)
- BigQuery / PostgreSQL / MySQL DDL output
- Python 3.11+

## Scenarios

[For each scenario, 2-3 lines + example command + sample output schema]

## Architecture

[Architecture diagram showing CLI → config → scenario → quality → docs]
[Brief explanation of RNG isolation pattern]

## Examples

See [examples/](examples/) for full quickstart scripts:
- `retail_quickstart.py` — basic e-commerce dataset
- `saas_promptforge.py` — SaaS with usage-based pricing
- `fintech_demo.py` — payment funnel with fraud signals

## Configuration

[Brief config reference + link to full docs]

## Development

```bash
git clone https://github.com/ryszard-twardy/synth-datagen
cd synth-datagen
pip install -e ".[test]"
pre-commit install
pytest
```

## Built with

- [Typer](https://typer.tiangolo.com/) — CLI
- [Pydantic v2](https://docs.pydantic.dev/) — config
- [NumPy](https://numpy.org/) — RNG and statistics
- [Pandas](https://pandas.pydata.org/) — data structures
- [Hypothesis](https://hypothesis.readthedocs.io/) — property tests

## License

MIT. See [LICENSE](LICENSE).

## Citing

If you use synth-datagen in academic work or blog posts, please cite:
[BibTeX or simple citation format]
```

### Step 2: docs/ directory

Create with MkDocs Material (lightweight, looks great):

```bash
pip install mkdocs-material
mkdocs new docs
```

Structure:
```
docs/
├── mkdocs.yml
├── docs/
│   ├── index.md           (landing page — same as README essentially)
│   ├── quickstart.md
│   ├── scenarios/
│   │   ├── retail.md      (with sample output, full config reference)
│   │   ├── saas.md
│   │   ├── fintech.md
│   │   └── logistics.md
│   ├── architecture/
│   │   ├── rng-isolation.md
│   │   ├── distributions.md
│   │   └── quality-injection.md
│   ├── recipes/
│   │   ├── powerbi-loading.md
│   │   ├── bigquery-loading.md
│   │   └── postgres-loading.md
│   ├── api/
│   │   └── reference.md   (auto-generated from docstrings via mkdocstrings)
│   └── changelog.md       (mirrors CHANGELOG.md)
```

Set up GitHub Pages deployment via .github/workflows/docs.yml.

### Step 3: CHANGELOG.md (Keep a Changelog format)

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- [...]

### Changed
- [...]

### Fixed
- [...]

## [0.2.0] — YYYY-MM-DD

### Added
- Initial public release
- Scenarios: retail, saas, fintech, logistics
- Configurable quality injection
- Auto-documentation output
```

### Step 4: CONTRIBUTING.md

Standard template covering:
- Development setup
- Running tests
- Conventional commits
- PR checklist
- How to add a new scenario

### Step 5: SECURITY.md

Standard template:
- Supported versions
- Reporting vulnerabilities
- Disclosure process

### Step 6: Update pyproject.toml metadata

```toml
[project]
name = "synth-datagen"
version = "0.2.0"
description = "Realistic synthetic business data with referential integrity, industry-calibrated distributions, and configurable quality injection."
authors = [{name = "Ryszard Twardy", email = "..."}]
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
keywords = ["synthetic-data", "data-generation", "testing", "etl", "portfolio"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Testing",
    "Topic :: Database",
]

[project.urls]
Homepage = "https://github.com/ryszard-twardy/synth-datagen"
Documentation = "https://ryszard-twardy.github.io/synth-datagen"
Issues = "https://github.com/ryszard-twardy/synth-datagen/issues"
Changelog = "https://github.com/ryszard-twardy/synth-datagen/blob/main/CHANGELOG.md"
```

## DELIVERABLE

- [ ] README.md ≤ 300 lines, scannable, with quickstart that works copy-paste
- [ ] docs/ site builds and deploys via GitHub Pages
- [ ] CHANGELOG.md with v0.2.0 release notes
- [ ] CONTRIBUTING.md and SECURITY.md
- [ ] pyproject.toml with full metadata for PyPI
- [ ] Every code example in README and docs/ has been verified to run successfully

## VERIFICATION
Before declaring complete, run:
```bash
# Build docs
mkdocs build --strict

# Verify README examples
bash -c 'cd /tmp && pip install -e /path/to/synth-datagen && synth-datagen retail --seed 42 --scale 100 --output-dir /tmp/test_readme && ls /tmp/test_readme'

# Smoke test on fresh clone
rm -rf /tmp/synth-clone && git clone . /tmp/synth-clone && cd /tmp/synth-clone && pip install -e ".[test]" && pytest
```

## SUCCESS CRITERIA
- A new contributor can clone, install, run tests, and contribute in < 10 minutes
- README answers "what is this and why should I care" in the first 30 seconds of reading
- The docs site looks professional (no broken links, no empty pages)
- The repo is publishable to PyPI without additional changes
```

---

## Optional Phase 5 — Public release

After Phases 1-4, you have a clean, tested, documented repo. To publish:

```bash
# Tag release
git tag v0.2.0
git push origin v0.2.0

# Publish to PyPI
pip install build twine
python -m build
twine upload dist/*

# Make repo public on GitHub
# Update LinkedIn, portfolio, etc.
```

---

## Time budget summary

| Phase | Agent work | Your review | Total wall time |
|-------|-----------|-------------|-----------------|
| 0. Setup | 10 min | — | 10 min |
| 1. Audit | 1-2h | 30 min | 2-3h |
| 2. Refactor | 4-6h | 1h | 5-7h |
| 3. Tests | 4-6h | 30 min | 4-6h |
| 4. Docs | 2-3h | 30 min | 3-4h |
| **Total** | **11-17h** | **2.5-3h** | **14-20h** |

Realistically: 2-3 calendar days of focused work, or 1 week with 2-3 hours/day.

---

## Tips for running this with the agent

**Keep prompts in a `prompts/` folder in the repo.** Don't paste from chat history — agents lose context across long conversations. Store the audit prompt as `prompts/01_audit.md`, the refactor prompt as `prompts/02_refactor.md`, etc. Open a fresh chat for each phase.

**Always start a phase by saying: "Read `prompts/0X_<phase>.md` and execute it."** This forces the agent to load the full context cleanly.

**When the agent suggests a fix, ask "what test proves this works?"** before letting it commit. This is the Superpowers `verification-before-completion` skill in action.

**If the agent hits 3 failed attempts on the same problem, stop the session and brainstorm with it before continuing.** This is the Superpowers escape hatch — don't let it grind.

**For Phase 2, work on one finding at a time.** Don't batch multiple findings into one agent session — testing isolation breaks down and bugs hide.

**For Phase 3, run `pytest` yourself between agent sessions.** Don't trust the agent's "tests pass" without seeing it locally.

---

## Why this workflow works

It mirrors how senior engineering teams actually work: audit before refactoring, test before changing, document before releasing. The Superpowers skills enforce discipline that's hard to maintain manually — they prevent the agent from skipping steps you'd want it to take.

The key insight: most coding agents fail not because they can't write code, but because they skip the steps between problems and solutions. They jump straight to "fix" without "understand." The Superpowers methodology blocks that pattern. Combined with explicit, structured prompts per phase, you get an agent that behaves like a senior engineer for the duration of this project.

When this is done, your `synth-datagen` repo will be a credible portfolio piece on its own — separate from Kupferkanne and the SaaS dashboard. In interviews, you'll be able to point at it and say "I built the engine that powers my portfolio data" — a story most junior candidates can't tell.
