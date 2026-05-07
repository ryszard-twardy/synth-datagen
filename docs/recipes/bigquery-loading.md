# Loading into BigQuery

`synth-datagen` outputs CSV and Parquet. BigQuery loads both. This recipe walks through GCS → BigQuery for a clean dataset, plus the `saas-v3` audit-CSV pattern for staging-table workflows.

## Clean path: Parquet via GCS

Parquet is preferred — it keeps dtypes, doesn't need a schema declaration, and loads roughly 2× faster than CSV.

```bash
# 1. Generate with Parquet output
synth-datagen retail --seed 42 --output ./out/retail \
    --rows fact_orders=100000,fact_order_items=300000,fact_payments=100000 \
    --export-parquet

# 2. Upload to GCS
gsutil -m cp -r ./out/retail/parquet/*.parquet \
    gs://your-bucket/synth-datagen/retail/parquet/

# 3. Load each table (one per Parquet file)
for table in dim_customers dim_products dim_stores dim_date \
             dim_promotions fact_orders fact_order_items \
             fact_payments bridge_order_promotions; do
  bq load \
    --source_format=PARQUET \
    --autodetect \
    your_project:retail.${table} \
    gs://your-bucket/synth-datagen/retail/parquet/${table}.parquet
done
```

`--autodetect` works because Parquet carries column types. No DDL needed.

## Schema-driven path: use the generated DDL

If you want the table created with explicit BigQuery types, the `schema.sql` file generated alongside the data is *Postgres-flavoured*. BigQuery's standard SQL accepts most of it (`VARCHAR(n)` → `STRING`, `TIMESTAMP` → `TIMESTAMP`), but you'll need to translate:

```bash
# Generate Postgres-flavoured DDL (default)
synth-datagen retail --output ./out/retail --export-parquet

# Quick sed pass to convert Postgres → BigQuery (rough but enough for fixtures)
sed -e 's/VARCHAR([0-9]*)/STRING/g' \
    -e 's/TEXT/STRING/g' \
    -e 's/INT/INT64/g' \
    -e 's/BIGINT/INT64/g' \
    -e 's/DECIMAL([0-9,]*)/NUMERIC/g' \
    -e 's/BOOLEAN/BOOL/g' \
    out/retail/schema.sql > schema.bq.sql

bq query --use_legacy_sql=false < schema.bq.sql
```

A v0.3.x feature is a native BigQuery dialect for the SQL exporter. Until then, the sed snippet is the path.

## Staging-table pattern (audit-grade dirty CSVs)

The `saas-v3` sub-app's `audit_093.yaml` profile generates CSVs that intentionally contain malformed dates and other quality issues. **Do not load these into typed columns directly** — they fail. The intended pattern is a two-step staging:

```bash
# 1. Generate audit dataset
synth-datagen saas-v3 generate \
    --config configs/saas_v3.audit_093.yaml \
    --mode dirty \
    --output ./out/saas_v3_audit
```

```sql
-- 2. Stage as STRING in BigQuery
CREATE OR REPLACE TABLE staging.saas_accounts_raw (
    account_id STRING,
    company_name STRING,
    plan_tier STRING,
    created_at_str STRING,         -- intentionally string; will fail-typed at clean step
    mrr_str STRING                 -- ditto
);

LOAD DATA OVERWRITE staging.saas_accounts_raw
    FROM FILES (
        format = 'CSV',
        uris = ['gs://your-bucket/synth-datagen/saas_v3_audit/accounts.csv'],
        skip_leading_rows = 1
    );

-- 3. Run your validators (Great Expectations / Soda / dbt tests / etc.)
--    against staging.saas_accounts_raw to catch the malformed rows.

-- 4. Cleanse and promote to typed table
CREATE OR REPLACE TABLE prod.saas_accounts AS
SELECT
    account_id,
    company_name,
    plan_tier,
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', created_at_str) AS created_at,
    SAFE_CAST(mrr_str AS NUMERIC) AS mrr
FROM staging.saas_accounts_raw
WHERE
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', created_at_str) IS NOT NULL
    AND SAFE_CAST(mrr_str AS NUMERIC) IS NOT NULL;
```

The audit profile injects ~0.93 % defects per active check, including `bad_date_formats`. The clean step's `WHERE` clause filters them out, and you can compare row counts pre/post to measure your DQ rate.

## Partitioning recommendation

For `fact_orders`, `transactions`, `events`, `feature_usage`, `shipments` — partition by the canonical date column (`created_at`, `event_at`, etc.). The synthetic data is already date-distributed across the period window, so partition pruning is meaningful out of the box.

```sql
CREATE TABLE prod.fact_orders
PARTITION BY DATE(created_at)
CLUSTER BY customer_id
AS SELECT * FROM staging.fact_orders_raw;
```

## Refresh cadence for portfolio demos

If you're shipping a "live" BigQuery-backed dashboard, regenerate weekly with `--seed $(date +%V)`, push the new Parquet to GCS, and run a `LOAD DATA OVERWRITE`. Cost is bytes-loaded only; with 100K-row scenarios that's pennies a week.
