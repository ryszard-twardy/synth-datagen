# Quickstart

This page gets you from a clean machine to a generated retail dataset in under five minutes. Two install paths are documented: from source (today) and from PyPI (from v0.2.0 onward).

## Prerequisites

- Python 3.11, 3.12, or 3.13
- [uv](https://docs.astral.sh/uv/) (recommended) — or plain `python -m venv` + `pip` works fine

## Install

=== "From source (today)"

    ```bash
    git clone https://github.com/ryszard-twardy/synth-datagen
    cd synth-datagen
    uv venv
    source .venv/bin/activate                # PowerShell: .\.venv\Scripts\Activate.ps1
    uv pip install -e ".[test]"
    ```

=== "From PyPI (from v0.2.0 onward)"

    ```bash
    pip install synth-datagen
    ```

Verify the install:

```bash
synth-datagen --help
synth-datagen scenarios
```

The second command should print `retail`, `saas`, `fintech`, `logistics`.

## First dataset (retail, ~6 seconds)

```bash
synth-datagen retail --seed 42 --output ./out/retail \
    --rows fact_orders=500,fact_order_items=1500,fact_payments=500 \
    --export-parquet
```

Expected output (truncated):

```
------------------------------- synthetic-data --------------------------------
Scenario : retail
Schema   : star
Dialect  : postgres
Seed     : 42
Output   : out\retail
DQ level : none
-------------------------------------------------------------------------------
Tables   : ['dim_customers', 'dim_products', 'dim_stores', 'dim_date',
            'dim_promotions', 'fact_orders', 'fact_order_items',
            'fact_payments', 'bridge_order_promotions']
-------------------------------------------------------------------------------
[OK] SQL DDL written -> out\retail\schema.sql
[OK] Data dictionary -> out\retail\data_dictionary.md
[OK] ERD (Mermaid)  -> out\retail\erd.md
Done! 29,807 rows in ~6s -> out\retail
```

You should now see 21 files under `out/retail/`:

| File | What it is |
|---|---|
| 9 × `*.csv` | One per table |
| 9 × `parquet/*.parquet` | Same data, columnar |
| `schema.sql` | Postgres-dialect DDL (override with `--dialect`) |
| `data_dictionary.md` | Per-table column descriptions, dtypes, semantic types |
| `erd.md` | Mermaid ER diagram of the star schema |

## Inject data-quality issues

The same dataset, but with intentional malformed rows for ETL practice:

```bash
synth-datagen retail --seed 42 --output ./out/retail-dirty \
    --rows fact_orders=500,fact_order_items=1500,fact_payments=500 \
    --data-quality medium
```

`--data-quality medium` injects missing values, format drift, duplicates, and out-of-range outliers across all tables. **Referential integrity is preserved** — the dirty data is realistic; it's not garbage. See [Architecture › Quality injection](architecture/quality-injection.md) for what each level produces.

## Try other scenarios

```bash
synth-datagen saas --seed 42 --output ./out/saas \
    --rows accounts=200,users=800,events=3000 --data-quality medium

synth-datagen fintech --seed 42 --output ./out/fintech \
    --rows customers=200,transactions=2000

synth-datagen logistics --seed 42 --output ./out/logistics \
    --rows shipments=300,shipment_items=900
```

Each scenario has a dedicated page — see the [scenarios overview](scenarios/index.md).

## Use the Python API instead

Anything the CLI can do, you can do from Python:

```python
from pathlib import Path

from synth_datagen.config import (
    DataQuality, DataQualityConfig, Dialect,
    GeneratorConfig, Scenario, SchemaType,
)
from synth_datagen.pipeline import run_pipeline

config = GeneratorConfig(
    scenario=Scenario.SAAS,
    schema_type=SchemaType.STAR,
    dialect=Dialect.POSTGRES,
    seed=42,
    output_dir=Path("./out/saas"),
    row_overrides={"accounts": 200, "users": 800, "events": 3_000},
    data_quality=DataQualityConfig(level=DataQuality.MEDIUM),
)
run_pipeline(config)
```

The full set of public types is in the [API reference](api/reference.md), and three runnable scripts live in [`examples/`](https://github.com/ryszard-twardy/synth-datagen/tree/main/examples).

## What if I see…

??? failure "`Retail requires fact_payments to equal fact_orders.`"

    The retail scenario enforces a 1:1 relationship between orders and payments. Pass both row counts together:

    ```
    --rows fact_orders=500,fact_payments=500
    ```

??? failure "`sqlite3.OperationalError: too many SQL variables`"

    SQLite's default parameter limit is hit by larger tables at the default `--chunk-size 50000`. Either drop `--export-sqlite` (CSV + Parquet are still emitted) or pass a smaller `--chunk-size 200`. A real fix that auto-chunks the SQLite exporter is tracked outside Phase 4.

??? failure "`Missing runtime dependency 'faker'.`"

    The package was installed without runtime deps. Re-run `uv pip install -e ".[test]"` (the `[test]` extra installs everything you need to develop) or `pip install synth-datagen` (which pulls in runtime deps automatically).
