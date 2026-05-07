# Loading into Postgres

The fastest path is the auto-generated `schema.sql` plus `\copy` for the CSVs. With `--export-dml` you get inserts instead, which is slower but works without a `psql` client.

## `\copy` path (recommended)

```bash
# 1. Generate with default Postgres dialect
synth-datagen retail --seed 42 --output ./out/retail \
    --rows fact_orders=100000,fact_order_items=300000,fact_payments=100000

# 2. Create the schema
psql -d mydb -f ./out/retail/schema.sql

# 3. \copy each CSV (handles large files; runs client-side)
psql -d mydb <<'SQL'
\copy dim_customers          FROM 'out/retail/dim_customers.csv'          CSV HEADER;
\copy dim_products           FROM 'out/retail/dim_products.csv'           CSV HEADER;
\copy dim_stores             FROM 'out/retail/dim_stores.csv'             CSV HEADER;
\copy dim_date               FROM 'out/retail/dim_date.csv'               CSV HEADER;
\copy dim_promotions         FROM 'out/retail/dim_promotions.csv'         CSV HEADER;
\copy fact_orders            FROM 'out/retail/fact_orders.csv'            CSV HEADER;
\copy fact_order_items       FROM 'out/retail/fact_order_items.csv'       CSV HEADER;
\copy fact_payments          FROM 'out/retail/fact_payments.csv'          CSV HEADER;
\copy bridge_order_promotions FROM 'out/retail/bridge_order_promotions.csv' CSV HEADER;
SQL
```

Load order matters because the DDL declares foreign-key constraints. `dim_*` tables first, then `fact_orders` (FKs to all dims), then `fact_order_items` and `fact_payments` (FK to `fact_orders`), then `bridge_order_promotions`.

A 100K-order dataset loads in under 30 seconds on a modest local Postgres.

## DML path (when you don't have shell access)

```bash
synth-datagen retail --output ./out/retail --export-dml
psql -d mydb -f ./out/retail/schema.sql
psql -d mydb -f ./out/retail/insert_dml.sql
```

The DML file is one `INSERT INTO ... VALUES (...), (...);` per table, batched. Slower than `\copy` (~5×), but it's a single file you can paste into `pgAdmin` or any GUI.

## Choosing a dialect

```bash
synth-datagen retail --dialect postgres --output ./out/retail   # default
synth-datagen retail --dialect mysql    --output ./out/retail
synth-datagen retail --dialect sqlite   --output ./out/retail
synth-datagen retail --dialect sqlserver --output ./out/retail
```

The `schema.sql` and the `insert_dml.sql` (when `--export-dml`) reflect the chosen dialect. The CSVs themselves are dialect-neutral.

## Indexing for analytics workloads

The auto-generated DDL declares only PK and FK constraints. For analytics queries on a star schema, add covering indexes after load:

```sql
-- Order date is the most common filter
CREATE INDEX idx_fact_orders_date_id ON fact_orders (date_id);

-- Customer drill-down
CREATE INDEX idx_fact_orders_customer ON fact_orders (customer_id, date_id);

-- Line-item join
CREATE INDEX idx_fact_order_items_order ON fact_order_items (order_id);

-- Bridge table lookups go both directions
CREATE INDEX idx_bridge_promo ON bridge_order_promotions (promotion_id);
```

For a 1M-order workload, additional `CLUSTER` ordering on `fact_orders (date_id)` halves typical analytics query time. For smaller demos it's overkill.

## Constraint validation

The schema declares `NOT NULL` only on PKs. With `--data-quality` ≥ `medium`, non-PK columns can contain `NULL` values — your application is expected to handle them, or you should layer a cleansing step (a `prod.<table>` view that filters `WHERE col IS NOT NULL`) on top of the loaded raw tables.

If you want strict-typed loading (i.e. the load fails when malformed values are present), use a staging-table pattern: load CSV → `STAGING.<table>_raw` with all columns as `TEXT`, validate, cast into `<table>`. The same pattern documented in [Loading into BigQuery](bigquery-loading.md) translates directly to Postgres.

## Multi-database in one script

Need to load all four scenarios into one Postgres database? The dialect-agnostic CSVs let you do this with a small bash loop:

```bash
for scenario in retail saas fintech logistics; do
  synth-datagen "$scenario" --output "./out/${scenario}"
  createdb "synth_${scenario}" || true
  psql -d "synth_${scenario}" -f "./out/${scenario}/schema.sql"
  for csv in ./out/${scenario}/*.csv; do
    table=$(basename "$csv" .csv)
    psql -d "synth_${scenario}" -c "\copy ${table} FROM '${csv}' CSV HEADER;"
  done
done
```

This gives you four separate databases (one per scenario) populated and ready to query.
