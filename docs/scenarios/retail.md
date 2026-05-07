# Retail

A 9-table star schema modelling a multi-store, multi-channel e-commerce business. Customer segments drive discount and order-frequency variation; promotions attach to orders via a bridge table; payment totals reconcile to line-item subtotals.

## Tables

| Table | Kind | Default rows (no `--rows` override) | Notes |
|---|---|---|---|
| `dim_customers` | dim | 20,000 | Segment-aware (`new`, `casual`, `loyal`, `vip`); attaches lifetime metrics post-fact |
| `dim_products` | dim | 5,000 | Categories, prices, margin bands |
| `dim_stores` | dim | 200 | Channel mix (online / brick / hybrid) |
| `dim_date` | dim | period-driven | One row per day across the configured period; warehouse `YYYYMMDD` int key |
| `dim_promotions` | dim | 150 | Discount %, validity windows |
| `fact_orders` | fact | 80,000 | Header — one row per order |
| `fact_order_items` | fact | 200,000 | Line items — averages ~2.5× `fact_orders` |
| `fact_payments` | fact | 80,000 | **1:1 with `fact_orders`** (validated) |
| `bridge_order_promotions` | bridge | 30,000 | M:N attaching promotions to orders |

The defaults above match `src/synth_datagen/generators/retail_builder.py` at v0.2.0; verify with `git grep 'ov.get(\"<table>\"' src/synth_datagen/generators/`.

The `--rows` flag accepts overrides per table:

```bash
synth-datagen retail --rows fact_orders=200000,fact_order_items=600000,fact_payments=200000
```

`fact_payments` must equal `fact_orders` or the Pydantic validator rejects the config — that 1:1 invariant is the engine's strictest constraint.

## Sample command

```bash
synth-datagen retail \
    --seed 42 \
    --output ./out/retail \
    --rows fact_orders=10000,fact_order_items=30000,fact_payments=10000 \
    --data-quality light \
    --dialect postgres \
    --export-parquet --export-dml
```

## Sample output

```
out/retail/
├── bridge_order_promotions.csv
├── data_dictionary.md
├── dim_customers.csv         dim_products.csv          dim_stores.csv
├── dim_date.csv              dim_promotions.csv
├── erd.md
├── fact_orders.csv           fact_order_items.csv      fact_payments.csv
├── parquet/                  ← matching .parquet files (with --export-parquet)
├── schema.sql                ← Postgres DDL
└── insert_dml.sql            ← INSERT statements (with --export-dml)
```

A 10K-order run finishes in ~6 seconds and writes ~30K rows total.

## Schema highlights

- **`fact_orders`**: `order_id` PK, FKs to `customer_id`, `store_id`, `date_id`. Carries `status` (`new`/`completed`/`cancelled`/`returned`), `created_at`, `total_amount`. Cancelled and returned orders are excluded from customer lifetime metrics.
- **`fact_order_items`**: `order_item_id` PK, FK to `order_id`. Carries `quantity`, `unit_price`, `line_amount`. The sum of `line_amount` per order matches `fact_orders.total_amount` (within rounding).
- **`fact_payments`**: `payment_id` PK, **1:1** with `fact_orders` via `order_id`. `paid_amount == total_amount` for completed orders.
- **`bridge_order_promotions`**: `(order_id, promotion_id)` composite key. Allows multiple promotions per order; allows the same promotion across many orders.
- **`dim_customers`** carries `segment`, `signup_date`, plus three reverse-derived metrics: `lifetime_value`, `last_order_at`, `total_orders` (all populated from `fact_orders` after generation, so the dim is internally consistent with the facts).

## Discount variation

`--discount-variation` (on by default) enables segment-aware discount distributions: VIPs get steeper discounts more often, new customers see promotional intro pricing, churned customers receive aggressive win-back offers. Pass `--no-discount-variation` for a uniform distribution that's better for stress-testing pricing models.

## Auto-generated docs

Every retail run writes:

- `data_dictionary.md` — every column with its dtype, semantic type, and inferred description.
- `erd.md` — a Mermaid ER diagram. Drop it into any Markdown viewer or paste it directly into a GitHub README.

## Python API equivalent

```python
from synth_datagen.config import (
    DataQuality, DataQualityConfig, Dialect,
    GeneratorConfig, Scenario, SchemaType,
)
from synth_datagen.pipeline import run_pipeline

config = GeneratorConfig(
    scenario=Scenario.RETAIL,
    schema_type=SchemaType.STAR,
    dialect=Dialect.POSTGRES,
    seed=42,
    output_dir="./out/retail",
    row_overrides={
        "fact_orders": 10_000,
        "fact_order_items": 30_000,
        "fact_payments": 10_000,
    },
    data_quality=DataQualityConfig(level=DataQuality.LIGHT),
    discount_variation=True,
    export_parquet=True,
)
run_pipeline(config)
```

The full runnable example is at [`examples/quickstart_retail.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/examples/quickstart_retail.py).
