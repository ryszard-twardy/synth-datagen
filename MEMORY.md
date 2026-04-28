# Repository Memory

## Purpose

`synthetic_data` is a Python synthetic dataset generator for portfolio-grade analytics data. It contains:

- classic v2-style scenario generators for `retail`, `saas`, `fintech`, and `logistics`,
- a monthly retail sales wrapper with resumable month-range exports,
- a dedicated YAML-driven `saas_v3` engine,
- a dedicated Kupferkanne RFM star-schema generator.

Core repo goals:

- deterministic output by seed,
- realistic business-rule coherence,
- configurable dirty-data injection,
- test-backed export contracts.

## Repo Shape

Top-level directories and files:

- `src/`: implementation
- `tests/`: regression and contract tests
- `configs/`: YAML profiles for SaaS v3, monthly sales, and Kupferkanne
- `output/`: generated datasets; currently contains monthly Kupferkanne outputs
- `scripts/`: helper scripts, including monthly-sales helpers
- `README.md`: full product and workflow docs
- `quick_guide_README.md`: fast-start command reference
- `AGENTS.md`: Codex/ECC local workflow notes
- `pyproject.toml`: package metadata, dependencies, console scripts, pytest config

Important `src/` entrypoints:

- `src/main.py`: classic scenario CLI
- `src/monthly_sales_cli.py`: monthly retail sales CLI
- `src/saas_v3/cli.py`: SaaS v3 CLI
- `src/kupferkanne_rfm_cli.py`: Kupferkanne RFM CLI
- `src/kupferkanne_rfm.py`: Kupferkanne generator/export contract
- `src/kupferkanne_rfm_config.py`: Kupferkanne YAML config models

Important test files:

- `tests/test_kupferkanne_rfm_generation.py`
- `tests/test_kupferkanne_rfm_cli.py`
- `tests/test_kupferkanne_rfm_config.py`
- `tests/test_monthly_sales_generation.py`
- `tests/test_saas_v3_engine.py`
- `tests/test_determinism.py`

## Runtime Notes

- `pyproject.toml` requires Python `>=3.11`.
- In this workspace, the repo-local venv at `.venv` is the reliable interpreter for tests and CLI verification.
- System `python` did not have `pytest`; use `.\.venv\Scripts\python.exe` for test runs.
- This checkout did not appear to be a Git working tree when inspected, so do not assume `git status` is available.
- PowerShell commands in repo docs are already written in single-line form and work well on Windows.

## Main Workflows

### Install / bootstrap

Recommended:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Run full tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

### Classic scenario generation

```powershell
python -m src.main generate --scenario retail --output ./out/retail --seed 42
python -m src.main generate --scenario saas --output ./out/saas --seed 42
synthetic-data generate --scenario fintech --output ./out/fintech --seed 42
synthetic-data generate --scenario logistics --output ./out/logistics --seed 42
```

### Monthly retail sales

```powershell
synthetic-monthly-sales generate --profile-config configs/monthly_sales.audit_growth_2023_2026.yaml --output ./out/monthly_sales_audit_2023_2026
synthetic-monthly-sales generate --month 2025-04 --orders-per-month 5000 --layout sales-files --include-flat --resume-from ./out/monthly_sales_files --output ./out/monthly_sales_files
```

### SaaS v3

```powershell
synthetic-saas generate --config configs/saas_v3.default.yaml --mode both --output ./out/saas_v3_default
synthetic-saas smoke-test --config configs/saas_v3.smoke.yaml --output ./out/saas_v3_smoke
synthetic-saas validate --config configs/saas_v3.audit_093.yaml --mode dirty --run-root ./out/saas_v3_audit_093
```

### Kupferkanne RFM

```powershell
.\.venv\Scripts\python.exe -m src.kupferkanne_rfm_cli generate --config configs/kupferkanne_rfm_v3.yaml --output output/monthly/line_number_header_fix_smoke --seed 42
```

The installed console script also exists:

```powershell
synthetic-rfm-kupferkanne generate --config configs/kupferkanne_rfm_v3.yaml --output ./output
```

## Kupferkanne Contract

Kupferkanne is a dedicated flow, not a thin wrapper over the classic monthly-sales engine.

Key files:

- config: `configs/kupferkanne_rfm_v3.yaml`
- engine/export logic: `src/kupferkanne_rfm.py`
- CLI: `src/kupferkanne_rfm_cli.py`
- baseline generated run: `output/monthly/2026-03-31_v3/`

Expected export shape:

- `dimensions/dim_customers.csv`
- `dimensions/dim_products.csv`
- `monthly/orders20YYMM.csv`
- `monthly/items20YYMM.csv`
- `manifest.json`
- `effective_config.yaml`
- `kupferkanne_rfm_schema.md`

Current `dim_customers.csv` contract:

- camelCase headers, not spaced labels
- default columns:
  - `CustomerID`
  - `SignupDate`
  - `CustomerArchetype`
  - `FirstName`
  - `LastName`
  - `Email`
  - `Phone`
  - `Country`
  - `State`
  - `City`
  - `Address`

Current `items20YYMM.csv` contract:

- columns:
  - `OrderID`
  - `LineNumber`
  - `ProductID`
  - `Quantity`
  - `UnitPrice`
  - `LineNetAmount`
- `LineNumber` is 1-based and sequential within each `OrderID` for clean-generated rows.
- clean line-item key is `(OrderID, LineNumber)`.
- final dirty exports may still contain duplicate `(OrderID, LineNumber)` rows because duplicate-row injection is intentionally preserved.

Important Kupferkanne validation behavior:

- `OrderValue` is intentionally absent from order shards.
- `manifest.json` tracks `dim_customers_columns` and row counts.
- generated schema doc should mention `LineNumber` and the clean `(OrderID, LineNumber)` identifier.

## Recent Changes

Most recent repo-level change set implemented here:

- added `LineNumber` to exported `items20YYMM.csv` files as the second column,
- kept internal `OrderLineNumber` and exported it as `LineNumber`,
- standardized `dim_customers.csv` export headers from spaced labels to camelCase,
- updated Kupferkanne schema doc generation to document `LineNumber` and the clean composite key,
- updated Kupferkanne tests to assert:
  - item export columns,
  - camelCase customer headers,
  - clean `(OrderID, OrderLineNumber)` uniqueness,
  - per-order sequential line numbering.

Related docs updated:

- `README.md`
- `quick_guide_README.md`

Smoke output used during verification:

- `output/monthly/line_number_header_fix_smoke/`

Verification result from that smoke run:

- generated successfully with seed `42`,
- row counts matched baseline `output/monthly/2026-03-31_v3/manifest.json`,
- `dim_customers.csv` headers were camelCase,
- `items202301.csv` had 6 columns including `LineNumber`,
- targeted Kupferkanne tests passed in `.venv`.

## Guardrails For Future Changes

- Preserve deterministic behavior by keeping seed-based flows stable unless the task explicitly changes generator logic.
- Treat generated outputs under `output/` as reference artifacts; avoid overwriting baseline snapshots unless the task explicitly calls for it.
- For Kupferkanne changes, update:
  - generator code,
  - tests,
  - generated schema doc behavior,
  - docs if the public export contract changes.
- If changing public columns or file contracts, verify both:
  - runtime smoke output,
  - matching test expectations.
- When running repo verification, prefer the repo venv:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

