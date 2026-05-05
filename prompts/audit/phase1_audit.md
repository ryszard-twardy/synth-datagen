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
npx ecc-agentshield scan --no-install
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
[From bandit + agentshield]

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
