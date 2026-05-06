# synthetic-data

Synthetic business dataset generator with:

- fixed-format production-style IDs
- cross-table business-rule coherence
- deterministic generation by seed
- configurable dirty-data injection for audit and demo use cases

## What Changed In This v3 Copy

- `customer_id`, `order_id`, and all other business PK/FK columns now use fixed-format string IDs such as `CU00000001` and `OR00000001`.
- `date_id` is a warehouse-style `YYYYMMDD` integer key.
- Retail order headers reconcile to order items.
- SaaS subscriptions, invoices, users, events, and feature usage follow valid timelines.
- Fintech transactions are generated in chronological ledger order and account balances reflect those ledgers.
- Logistics inventory, shipment items, and freight costs are internally consistent.
- Data-quality modes preserve ID formats, referential integrity, and parseable date/timestamp fields in the classic v2 pipeline.
- `saas_v3` adds YAML-driven lifecycle generation plus per-check defect rates for audit-grade dirty CSV generation.
- Only `--schema star` is supported. `3nf` and `mixed` are rejected explicitly.

## Installation

Prerequisite: Python 3.11 or 3.12.

From the repo root:

```bash
python -m pip install -e ".[test]"
```

If `python --version` shows Python 3.10.x, use a 3.11+ interpreter instead. On Windows, for example:

```bash
py -3.11 -m pip install -e ".[test]"
```

## Quick Start

Classic scenario entrypoints in the v3 repo:

```bash
python -m synth_datagen.main generate --scenario retail --output ./out/retail --seed 42
python -m synth_datagen.main generate --scenario saas --output ./out/saas --seed 42
```

Installed console entry points:

```bash
synthetic-data generate --scenario fintech --output ./out/fintech --seed 42
synthetic-monthly-sales generate --month 2025-01 --orders-per-month 5000 --layout combined
synthetic-saas generate --config configs/saas_v3.default.yaml --mode both --output ./out/saas_v3_default
synthetic-rfm-kupferkanne generate --config configs/kupferkanne_rfm_v3.yaml --output ./output/monthly/
```

Examples use single-line commands so they work in PowerShell as well as Bash.

## SaaS v3

Use `saas_v3` when you need a more controllable SaaS customer-success dataset with:

- YAML configuration
- clean and dirty output modes
- per-check defect rates
- audit-oriented dirty CSV exports before BigQuery loading

Use classic `src.main generate --scenario saas` when you only need the older v2 SaaS dataset with coarse `none|light|medium|heavy` quality levels.

### SaaS v3 Audit 0.93%

This repo now includes `configs/saas_v3.audit_093.yaml`, which targets roughly `0.93%` dirty rows per active check, including a deliberate `bad_date_formats` defect for raw CSV audit scenarios.

Recommended command:

```bash
synthetic-saas generate --config configs/saas_v3.audit_093.yaml --mode both --output ./out/saas_v3_audit_093
```

Equivalent module form:

```bash
python -m synth_datagen.saas_v3.cli generate --config configs/saas_v3.audit_093.yaml --mode both --output ./out/saas_v3_audit_093
```

Important: the dirty CSV in this profile is intended for staging and audit before BigQuery load. It intentionally contains malformed dates and other data issues, so it is not meant to be loaded directly into strict typed `DATE` or `TIMESTAMP` columns without a staging step.

### Other SaaS v3 Commands

Default realistic profile:

```bash
synthetic-saas generate --config configs/saas_v3.default.yaml --mode both --output ./out/saas_v3_default
```

Small smoke profile:

```bash
synthetic-saas smoke-test --config configs/saas_v3.smoke.yaml --output ./out/saas_v3_smoke
```

Validate an exported run:

```bash
synthetic-saas validate --config configs/saas_v3.audit_093.yaml --mode dirty --run-root ./out/saas_v3_audit_093
```

## Supported Scenarios

- `retail`
- `saas`
- `fintech`
- `logistics`
- `saas_v3` via `src.saas_v3.cli` or `synthetic-saas`
- `kupferkanne_rfm` via `src.kupferkanne_rfm_cli` or `synthetic-rfm-kupferkanne`

## ID Standard

- `customer_id`: `CU########`
- `order_id`: `OR########`
- other PK/FK columns: fixed semantic prefix plus 8-digit numeric body
- `date_id`: `YYYYMMDD`

The ID format is enforced in schema metadata and validated in tests.

## Data Quality Modes

Classic v2 pipeline:

`none`, `light`, `medium`, and `heavy` are still available, but v2 treats them as "dirty yet plausible":

- no negative synthetic IDs
- no typo corruption of IDs, dates, timestamps, status fields, or structured codes
- no broken foreign keys
- no invalid email/domain/SKU rewrites

SaaS v3 pipeline:

- defect rates are configured per check in YAML
- clean and dirty datasets are generated from the same seeded run
- dirty exports can include malformed raw values for audit scenarios, including bad date formats

## Validation

Run the full suite:

```bash
python -m pytest tests -q
```

The suite includes:

- PK/FK integrity
- ID regex and fixed-length checks
- retail header/detail reconciliation
- monthly retail sales range, flat extract, and resume checks
- SaaS lifecycle validation
- SaaS v3 dirty defect-rate validation
- fintech ledger chronology checks
- logistics inventory and shipment consistency checks
- data-quality safety checks for `light` and `heavy`

## Monthly Sales Script

The retail wrapper keeps the normalized engine schema and adds a CSV-style convenience layer:

- `combined/` writes the full requested range in the standard retail PK/FK tables
- `months/YYYY-MM/` writes self-contained monthly subsets trimmed to referenced dimensions
- `sales-files` writes shared dimension tables once plus monthly flat files like `sales_202501.csv`
- `monthly_sales_flat.csv` is optional and is derived from `fact_orders` plus `fact_order_items`
- `--resume-from` appends a new range onto a prior `combined/` snapshot while continuing IDs safely

Key options:

- `--start-date` / `--end-date` or `--month`
- `--orders-per-month`
- `--profile-config configs/monthly_sales.audit_growth_2023_2026.yaml`
- `--avg-items-per-order`
- `--layout monthly|combined|both|sales-files`
- `--include-flat`
- `--resume-from`
- `--data-quality none|light|medium|heavy`

Ready audit-growth profile:

```bash
synthetic-monthly-sales generate --profile-config configs/monthly_sales.audit_growth_2023_2026.yaml --output ./out/monthly_sales_audit_2023_2026
```

That profile generates monthly retail data from `2023-01-01` through `2026-03-31`, keeps monthly `fact_orders` under the configured cap of `5000`, applies a rising long-term trend with natural month-to-month dips, and injects audit-style bad data into normalized tables plus `monthly_sales_flat.csv`.

Shared dimensions plus monthly sales files:

```bash
synthetic-monthly-sales generate --start-date 2025-01-01 --end-date 2025-03-31 --orders-per-month 5000 --layout sales-files --include-flat --output ./out/monthly_sales_files
```

Append a single month of sales into an existing sales-files snapshot:

```bash
synthetic-monthly-sales generate --month 2025-04 --orders-per-month 5000 --layout sales-files --include-flat --resume-from ./out/monthly_sales_files --output ./out/monthly_sales_files
```

## Kupferkanne RFM

`Kupferkanne RFM` in v3 is a dedicated flow for the Erlangen pantry e-commerce brief. It does not reuse the classic monthly-sales wrapper because the project needs a different customer-behavior model, a richer product catalog, line-item generation, clustered audit defects, and a BigQuery-ready wildcard contract.

The generator builds clean internal order headers and line items, then exports a four-table star schema:

- `dimensions/dim_customers.csv`
- `dimensions/dim_products.csv`
- `monthly/orders202301.csv` ... `monthly/orders202603.csv`
- `monthly/items202301.csv` ... `monthly/items202603.csv`

The monthly fact shards stay analytics-friendly on purpose: `orders20*` matches `orders202301` ... `orders202603`, and `items20*` matches `items202301` ... `items202603`. This keeps `_TABLE_SUFFIX` aligned to `2301` through `2603` for both fact groups in BigQuery.

Every business setting lives in the dedicated YAML config, including:

- date range
- catalog and category shares
- archetype mix and acquisition curve
- country distribution
- seasonality and YoY growth
- discount behavior
- clustered dirty-data injection targets

Recommended command:

```bash
synthetic-rfm-kupferkanne generate --config configs/kupferkanne_rfm_v3.yaml --output ./output
```

Module form:

```bash
python -m synth_datagen.kupferkanne_rfm_cli generate --config configs/kupferkanne_rfm_v3.yaml --output ./output
```

The output directory contains `dimensions/`, `monthly/`, `manifest.json`, `effective_config.yaml`, and `kupferkanne_rfm_schema.md`.

Current star schema:

- `dim_customers`: `CustomerID`, `SignupDate`, `CustomerArchetype`, plus configurable customer enrichment fields
- `dim_products`: `ProductID`, `ProductName`, `ProductCategory`, `Brand`, `RetailPrice`, `UnitCost`, `MarginPct`
- `orders20YYMM`: `OrderID`, `CustomerID`, `OrderDate`, `OrderDiscountPct`, `BasketItemCount`
- `items20YYMM`: `OrderID`, `LineNumber`, `ProductID`, `Quantity`, `UnitPrice`, `LineNetAmount`

By default, `dim_customers.csv` also exports:

- `FirstName`
- `LastName`
- `Email`
- `Phone`
- `Country`
- `State`
- `City`
- `Address`

You can trim those optional customer columns in `configs/kupferkanne_rfm_v3.yaml`:

```yaml
output:
  dim_customers_extra_columns: []
```

Or keep only a subset:

```yaml
output:
  dim_customers_extra_columns: [first_name, email, city]
```

## Notes

- The original `synthetic_data` repo remains untouched.
- Sample outputs in `out/` are deterministic and can be regenerated with seed `42`.
- If you request incompatible row overrides, v2 fails fast instead of silently generating incoherent data.
