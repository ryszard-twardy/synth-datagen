# Quick Guide

Prerequisite: Python 3.11+.

Use single-line commands in PowerShell. If `python --version` shows Python 3.10.x, switch to a 3.11+ interpreter before installing.

## Local Venv

Quick setup for the project virtual environment in PowerShell:

```bash
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
synthetic-saas --help
```

## Kupferkanne RFM v3

Dedicated RFM flow with one YAML config, clean dimensions, and monthly star-schema fact shards:

```bash
synthetic-rfm-kupferkanne generate --config configs/kupferkanne_rfm_v3.yaml --output ./output
```

Module form:

```bash
python -m synth_datagen.kupferkanne_rfm_cli generate --config configs/kupferkanne_rfm_v3.yaml --output ./output
```

Important naming note for the repo default config:

```bash
orders20* -> orders202301, orders202302, ..., orders202603
items20* -> items202301, items202302, ..., items202603
```

`orders20YYMM.csv` is one row per order. `items20YYMM.csv` is one row per line item. `OrderValue` is intentionally absent; derive it downstream with `SUM(LineNetAmount) GROUP BY OrderID`.

Default `dim_customers.csv` exports all optional customer enrichment fields:

```yaml
output:
  dim_customers_extra_columns:
    - first_name
    - last_name
    - email
    - phone
    - state
    - city
    - address
```

Export headers use camelCase names, for example `CustomerID`, `SignupDate`, `FirstName`, `LastName`, `Email`, `Phone`, `Country`, `State`, `City`, `Address`.

Minimal customer dimension export:

```yaml
output:
  dim_customers_extra_columns: []
```

## SaaS Audit 0.93%

Raw audit CSVs with about `0.93%` dirty rows per active check, including malformed date strings before BigQuery staging:

```bash
synthetic-saas generate --config configs/saas_v3.audit_093.yaml --mode both --output ./out/saas_v3_audit_093
```

Module form:

```bash
python -m synth_datagen.saas_v3.cli generate --config configs/saas_v3.audit_093.yaml --mode both --output ./out/saas_v3_audit_093
```

## SaaS Smoke

Fast smoke run for a tiny clean + dirty SaaS v3 export:

```bash
synthetic-saas smoke-test --config configs/saas_v3.smoke.yaml --output ./out/saas_v3_smoke
```

## SaaS Default Realistic

Larger realistic SaaS v3 dataset with clean and dirty outputs:

```bash
synthetic-saas generate --config configs/saas_v3.default.yaml --mode both --output ./out/saas_v3_default
```

Validate an exported dirty run:

```bash
synthetic-saas validate --config configs/saas_v3.audit_093.yaml --mode dirty --run-root ./out/saas_v3_audit_093
```

## Retail

Classic v2 retail scenario:

```bash
python -m synth_datagen.main generate --scenario retail --output ./out/retail --seed 42
```

## Fintech

Classic v2 fintech scenario:

```bash
synthetic-data generate --scenario fintech --output ./out/fintech --seed 42
```

## Logistics

Classic v2 logistics scenario:

```bash
synthetic-data generate --scenario logistics --output ./out/logistics --seed 42
```

## Monthly Retail Sales

Monthly retail wrapper with combined and monthly layouts plus flat extract:

```bash
synthetic-monthly-sales generate --profile-config configs/monthly_sales.audit_growth_2023_2026.yaml --output ./out/monthly_sales_audit_2023_2026
```

Shared dimensions plus monthly sales files:

```bash
synthetic-monthly-sales generate --start-date 2025-01-01 --end-date 2025-03-31 --orders-per-month 5000 --layout sales-files --include-flat --output ./out/monthly_sales_files
```

Append one extra sales month into the same snapshot:

```bash
synthetic-monthly-sales generate --month 2025-04 --orders-per-month 5000 --layout sales-files --include-flat --resume-from ./out/monthly_sales_files --output ./out/monthly_sales_files
```

Classic single-month example:

```bash
python scripts/generate_monthly_sales.py generate --month 2025-01 --orders-per-month 5000 --layout both --include-flat --output ./out/monthly_sales
```

Installed monthly entry point:

```bash
synthetic-monthly-sales generate --month 2025-01 --orders-per-month 5000 --layout combined
```

## Useful Flags

- `--scenario retail|saas|fintech|logistics`
- `--rows "fact_orders=5000,fact_order_items=15000,fact_payments=5000"`
- `--data-quality none|light|medium|heavy`
- `--export-sqlite`
- `--export-parquet`
- `--mode clean|dirty|both` for `synthetic-saas`

## Validate Tests

```bash
python -m pytest tests -q
```

## Demo Script

```bash
python run_demo.py
```
