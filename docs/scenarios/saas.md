# SaaS

A 7-table star schema modelling a B2B SaaS product with subscription billing, usage events, and feature-level engagement. Designed for product analytics, churn modelling, and feature-adoption funnels.

## Tables

| Table | Kind | Default rows (no `--rows` override) | Notes |
|---|---|---|---|
| `accounts` | dim | 5,000 | One row per company; `mrr` populated post-fact from active subscriptions |
| `users` | dim | 25,000 | Many-per-account; carries role and last-active timestamp |
| `features` | dim | 50 | Product features for usage attribution |
| `subscriptions` | fact | 6,000 | Plan, term, MRR, status; valid timeline (start ≤ end) |
| `feature_usage` | fact | 150,000 | (account_id, feature_id, period) usage counters |
| `events` | fact | 500,000 | Activity event log — login, action, page view |
| `invoices` | fact | 20,000 | Monthly recurring billing aligned to subscription terms |

The defaults above match `src/synth_datagen/generators/saas.py` at v0.2.0.

## Sample command

```bash
synth-datagen saas \
    --seed 42 \
    --output ./out/saas \
    --rows accounts=200,users=800,events=3000 \
    --data-quality medium \
    --export-parquet
```

A small saas run finishes in ~2 seconds.

## Sample output

```
out/saas/
├── accounts.csv         users.csv          features.csv
├── subscriptions.csv    feature_usage.csv  events.csv  invoices.csv
├── parquet/             ← matching .parquet files
├── schema.sql           ← Postgres DDL
├── data_dictionary.md
└── erd.md
```

## Schema highlights

- **`accounts.mrr`** is reverse-derived from active subscriptions, so it's always internally consistent with the subscription fact.
- **`subscriptions`** carries `plan`, `term` (`monthly` / `annual`), `status` (`trial` / `active` / `paused` / `churned`), `started_at`, `ended_at`. End ≥ start is enforced. Churned subscriptions have `ended_at`; active ones don't.
- **`invoices`** are issued monthly per active subscription; amounts derive from plan price × proration. Issue dates fall on or after the subscription start.
- **`feature_usage`** — when `--data-quality` ≥ `medium` injects "rank-bucket empty" cases, the engine falls back to the full feature list (a regression we hardened in Phase 3).
- **`events`** is the largest table; it dominates wall time. Trim it via `--rows events=N` for faster iteration.

## Sub-app: SaaS v3

If you need YAML-driven config, per-check defect rates, and audit-grade dirty CSV exports (e.g. for BigQuery staging), use the dedicated `saas-v3` sub-app:

```bash
synth-datagen saas-v3 generate \
    --config configs/saas_v3.audit_093.yaml \
    --mode both \
    --output ./out/saas_v3_audit
```

The shipped configs are:

- `configs/saas_v3.default.yaml` — realistic profile, clean output
- `configs/saas_v3.smoke.yaml` — small smoke profile
- `configs/saas_v3.audit_093.yaml` — ~0.93 % dirty rows per active check, including a deliberate `bad_date_formats` defect intended for staging-table audit before BigQuery load

The audit profile's dirty CSV is **not** safe to load directly into typed `DATE`/`TIMESTAMP` columns — that's the whole point. Stage to a `STRING` raw layer first.

### v0.2.1 — `plg-usage-based` sub-mode

The `saas-v3` engine now supports two modes via `run.mode` in YAML:

- `legacy` (default) — original 7-table output. Byte-stable across versions.
- `plg-usage-based` — emits an 8th table, `subscription_events`, and
  unlocks the `--benchmark-validation` CLI flag.

Reference config: [`configs/saas_v3.plg.yaml`](https://github.com/ryszard-twardy/synth-datagen/blob/main/configs/saas_v3.plg.yaml).

#### `subscription_events` schema

| column | type | notes |
|---|---|---|
| `event_id` | string | `sevt_NNNNNNNNNN` PK |
| `subscription_id` | string | FK → `subscriptions` |
| `account_id` | string | FK → `accounts` (denormalized) |
| `event_type` | enum | `new` \| `expansion` \| `contraction` \| `churn` \| `reactivation` |
| `event_date` | date | |
| `mrr_delta` | float | signed; `SUM(mrr_delta) GROUP BY account_id` equals current MRR ± 0.01 |
| `previous_mrr` | float | MRR immediately before the event |
| `new_mrr` | float | MRR immediately after the event |
| `reason` | string | Pareto-distributed for `churn`; tag for `expansion`/`contraction`; empty for `new`/`reactivation` |

The 5-movement decomposition is the source of truth for an MRR waterfall.
The MRR-balance invariant is verified by a Hypothesis property test
(`tests/property/test_saas_v3_invariants.py`) across 8 random seeds per
test run.

Reactivation events synthesize the "win-back" pattern: ~5% of churned
accounts (minimum 2 per smoke run) emit a `churn` event followed by a
`reactivation` event 30..365 days later, restoring MRR. This is enabled
only in `plg-usage-based` mode; legacy mode never produces reactivation
rows.

#### `--benchmark-validation`

```bash
synth-datagen saas-v3 generate \
    --config configs/saas_v3.plg.yaml \
    --mode clean \
    --output out/saas_v3_plg \
    --benchmark-validation
```

Computes industry KPIs and writes `benchmark_validation.md` to the run
root, comparing each metric to the configured target range:

| metric | computation | default range |
|---|---|---|
| `nrr` | `(start_mrr + expansion − contraction − churn) / start_mrr` over the trailing 12 months | `[1.05, 1.35]` |
| `grr` | `(start_mrr − contraction − churn) / start_mrr` (same window) | `≥ 0.85` |
| `lifetime_churn_rate` | unique churned accounts / unique accounts that ever had a `new` event | `≤ 0.40` |
| `trial_conversion_rate` | reserved for v0.3.0 (no `trials` table emitted in v0.2.1) | `[0.15, 0.40]` (skipped) |

Defaults are calibrated to KeyBanc 2024 SaaS Survey + Benchmarkit 2025.
Override per-config under the top-level `benchmarks:` block.

The flag exits non-zero (CLI exit code 1) on benchmark failure so CI can
detect drift. **Smoke-sized configs (≤ 100 accounts) are too small for
benchmark targets to hold reliably** — calibrate against portfolio-scale
runs. For shape testing without benchmark gating, omit `--benchmark-validation`.

In legacy mode, `--benchmark-validation` is silently a no-op (the report
is `skipped=True`, no md file is written, exit 0).

#### RNG salt

`saas_v3` is registered under salt `0x5AA50000` in
`src/synth_datagen/rng.py:SALT_REGISTRY`. All saas_v3 RNG draws derive
from `make_rng(seed, "saas_v3").spawn(N)` — no direct
`np.random.default_rng(...)` calls in saas_v3 scenario code. saas_v3
byte output shifted once at v0.2.1 (the migration commits); v0.3.0 will
pin it via `scripts/baseline_diff.py`.

## Python API equivalent

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
    row_overrides={
        "accounts": 200, "users": 800, "subscriptions": 400,
        "invoices": 1_000, "feature_usage": 2_000, "events": 3_000,
    },
    data_quality=DataQualityConfig(level=DataQuality.MEDIUM),
)
run_pipeline(config)
```

The runnable example is at [`examples/quickstart_saas.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/examples/quickstart_saas.py).
