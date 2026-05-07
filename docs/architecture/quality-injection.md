# Quality injection

`--data-quality {none,light,medium,heavy}` is the knob that turns clean generated output into ETL-practice fodder. This page documents the four levels, what they preserve, and what they corrupt.

## The four levels

| Level | Overall corruption rate | Use for |
|---|---|---|
| `none` | 0 % | Smoke tests, unit fixtures, anything where you assert exact values |
| `light` | ~0.5 % per check | "Real-world clean" — looks like production data after a basic clean step |
| `medium` | ~3 % per check | ETL practice — enough rough edges to need real cleaning logic |
| `heavy` | ~10 % per check | Stress-testing data-quality monitors and outlier detectors |

Each level is applied independently per **check**, so a row can be missing a value AND have a malformed timestamp AND be a near-duplicate. The percentage you see is per-check, not total — total corruption can stack.

## What's preserved at every level

These guarantees hold even at `heavy`:

- **PK uniqueness.** No table ever has duplicate primary keys.
- **FK validity.** Every foreign key still resolves to an existing row in the parent table.
- **PK/FK formats.** `CU00000001`-style IDs stay 10 characters wide. `YYYYMMDD` date keys stay 8-digit ints.
- **Date/timestamp parseability.** Even when timestamps are reformatted, they parse via `pandas.to_datetime`.
- **Schema.** No column is added, removed, or renamed.

These guarantees are what make the output usable. Garbage in / garbage out is too easy; the interesting case is "data that looks fine until you check carefully."

## What gets corrupted

The full list of injection checks lives in [`src/synth_datagen/exporters/quality.py`](https://github.com/ryszard-twardy/synth-datagen/tree/main/src/synth_datagen) (and is re-exported via `apply_data_quality`):

| Check | What it does | Affected at |
|---|---|---|
| Missing values | Replaces non-PK/non-FK values with `NaN` | `light`, `medium`, `heavy` |
| Format drift (numeric) | Reformats decimals as strings (`"1,234.56"`, `"1234,56"`) | `medium`, `heavy` |
| Format drift (date) | Reformats timestamps (`"2024-03-15"`, `"15/03/2024"`, `"Mar 15 2024"`) | `medium`, `heavy` |
| Trimmed strings | Adds leading/trailing whitespace | `light`, `medium`, `heavy` |
| Case drift | Random case for emails/codes (`"Foo@BAR.com"`) | `medium`, `heavy` |
| Near-duplicates | Re-emits a recent row with one field tweaked | `heavy` |
| Outlier amounts | Multiplies a numeric by 10× or 100× | `medium`, `heavy` |
| Out-of-range timestamps | Shifts timestamps outside the period window | `medium`, `heavy` |

`light` is intentionally limited to checks that don't break naive type-coercion: missing values and trimmed strings. A `light`-quality CSV loads cleanly into a strict-typed warehouse table.

`medium` is the sweet spot for ETL practice — enough rough edges to need cleaning logic, but every check is still individually catchable with standard validators (Great Expectations, Soda, dbt tests).

`heavy` is for stress-testing detection systems. Don't load `heavy` output directly into a strict schema; you'll get type-coercion errors. That's the point.

## Per-check defect rates (SaaS v3 only)

The `saas-v3` sub-app ships an `audit_093.yaml` profile with **per-check** defect rates instead of a global level. This lets you inject 0.93 % `bad_date_formats` while keeping every other check at 0 %, which is the realistic shape for "things our data team complained about" datasets.

The per-check pattern is currently SaaS-v3 specific; promoting it to the unified CLI is a v0.3.x backlog item.

## How it interacts with `--seed`

The corruption is also seeded. Same `--seed` + same `--data-quality` → same bytes, same corrupted rows in the same positions. This matters: tests can assert "row 47 of `accounts.csv` has a malformed `created_at`" and that assertion stays stable.

## Inspecting what got injected

There's no "manifest of corruptions" file (yet). To see what changed, generate twice — once at `none`, once at the level you want — and `diff` the outputs:

```bash
synth-datagen retail --seed 42 --output ./out/clean   --data-quality none   ...
synth-datagen retail --seed 42 --output ./out/dirty   --data-quality medium ...
diff -u ./out/clean/dim_customers.csv ./out/dirty/dim_customers.csv | head -40
```

This is the recommended workflow for building data-quality teaching exercises: ship the dirty file, keep the clean file as the answer key.
