# Phase 4 — Documentation & Publication Prep (extracted)

> Extracted from `prompts/audit/02_workflow.md` §"PHASE 4 — Documentation & Publication Prep"
> for direct execution per `prompts/00_master.md` §4 Step 4.
> Branch: `feat/docs`. Source-of-truth tag at session start: `v0.2.0-rc2`.

---

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

---

## Session-specific deliverables (overlay from /00_master/ §4 Step 4)

These extend/override the verbatim spec above based on this session's instructions:

- README rewrite **≤ 300 lines**, scannable, **architecture diagram via Mermaid**, examples for each scenario.
- MkDocs Material site setup (`mkdocs.yml` + `docs/` folder structure). `mkdocs build --strict` MUST succeed.
- CHANGELOG.md: move Phase-3 entries currently under `## [Unreleased]` to a new `## [0.2.0] — <date>` section per Keep a Changelog format. Keep `[Unreleased]` empty (skeleton).
- CONTRIBUTING.md (development setup, commit conventions, PR process).
- SECURITY.md (vulnerability reporting).
- pyproject.toml: keywords, classifiers, urls (homepage, documentation, repository, issues), license = "MIT", complete for PyPI.
- Verify version bump from `0.2.0-dev` to `0.2.0` at end (final commit before tag).

### Session constraints

- `mkdocs build --strict` must succeed.
- Every code example in README/docs verified to run (copy-paste from fresh clone + `uv` venv + `pip install -e ".[test]"`).
- README quickstart works copy-paste on Windows + macOS + Linux paths.
- Conventional Commits, NO co-authored-by trailer.
- Push `origin feat/docs` after each commit.
- At end of session: code-reviewer agent skill for diff review before declaring done.
- pytest must remain green throughout.

### Quickstart-command reality check (read before writing the README)

The verbatim Phase-4 spec uses flag names like `--scale`, `--output-dir`, and a console script `synth-datagen retail --seed 42 --scale 10000 --output-dir ./data`. The actual unified CLI shipped in Phase 2 (P1-2) uses:

```
synth-datagen <scenario> --seed 42 --rows fact_orders=10000 --output ./out/retail
```

(`--rows table=N,...` not `--scale`; `--output` not `--output-dir`; per `src/synth_datagen/cli.py`.)

The README must reflect the **actual CLI**, not the spec's placeholder commands. Verify each example works before committing.
