# Loading into Power BI

`synth-datagen` writes plain CSV (and optional Parquet) to disk. Power BI Desktop reads both natively. This recipe shows the fast path for star-schema scenarios.

## What you'll have on disk

After running e.g. `synth-datagen retail --output ./out/retail`, you'll see:

```
out/retail/
├── dim_customers.csv         dim_products.csv          dim_stores.csv
├── dim_date.csv              dim_promotions.csv
├── fact_orders.csv           fact_order_items.csv      fact_payments.csv
├── bridge_order_promotions.csv
├── data_dictionary.md        ← reference while modelling
└── erd.md                    ← Mermaid diagram of the relationships
```

The naming is deliberate: tables prefixed `dim_` are dimensions, `fact_` are facts, `bridge_` are M:N bridges. Power BI's auto-relationship detector will not get this right — wire relationships up manually using the ERD as your source of truth.

## Fast path: Get Data → Folder

1. **Get Data → More → File → Folder**, point it at `out/retail/`.
2. Filter the Folder query to `Extension = .csv` (drops the `.md` files).
3. Click **Combine & Transform** — Power Query loads each CSV as a separate table.
4. In the model view, drag relationships from each fact's foreign-key column to the matching dim's primary key:
    - `fact_orders.customer_id` → `dim_customers.customer_id`
    - `fact_orders.product_id` doesn't exist on the header; use `fact_order_items.product_id` → `dim_products.product_id`
    - `fact_orders.store_id` → `dim_stores.store_id`
    - `fact_orders.date_id` → `dim_date.date_id` (note: integer YYYYMMDD)
    - `fact_payments.order_id` → `fact_orders.order_id` (1:1, mark as one-to-one)
5. Set `dim_date` as the date table (right-click → Mark as date table → use `date` column).

## If you want Parquet instead

Generate with `--export-parquet`. Power BI 2.106+ reads Parquet via Get Data → File → Parquet. Parquet keeps the column dtypes (no string-to-number coercion in Power Query), which matters when `--data-quality` ≥ `medium` produces `"1,234.56"`-style decimal strings — Parquet preserves them as proper `Decimal128`.

## DirectQuery against SQLite

Generate with `--export-sqlite` to get a `<scenario>.db` file. Connect via the SQLite ODBC driver (Power BI doesn't ship a native SQLite connector, but the [SQLite ODBC](http://www.ch-werner.de/sqliteodbc/) driver works). DirectQuery against a 100K-row SQLite file is fast enough for portfolio demos and avoids an Import-mode refresh cycle.

??? warning "SQLite chunking issue"

    With the default `--chunk-size 50000` and tables larger than ~10K rows, the SQLite exporter hits SQLite's "too many SQL variables" limit. Either drop `--export-sqlite` (CSV + Parquet still work) or pass `--chunk-size 200`. A real fix is on the v0.3.x backlog.

## Date-table tip

`dim_date` is generated with the warehouse-style `date_id` integer key (e.g. `20240315`) and a real `date` column next to it. Always use the `date` column for Power BI's date intelligence — DAX `TOTALYTD` and friends require a real date, not the integer. The integer is there for joins, not for time-axis modelling.

## Refresh cycle

`synth-datagen` is deterministic by `--seed`. If your portfolio demo wants "fresh data every Monday", schedule a CI job that regenerates with `--seed $(date +%V)` (ISO week number) and pushes the CSV/Parquet to a known location. Power BI's Service auto-refresh then sees new bytes weekly without a code change.
