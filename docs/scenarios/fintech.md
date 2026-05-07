# Fintech

A 7-table payment ledger with chronologically valid transactions, account balances that reconcile to the ledger, card lifecycle (issue / expire / reissue), and an optional loan-and-repayment subsystem. Designed for reconciliation tutorials and fraud-signal exploration.

## Tables

| Table | Kind | Approx default size | Notes |
|---|---|---|---|
| `customers` | dim | 5,000 | Demographic profile, KYC tier |
| `accounts` | fact-ish | 6,000 | Per-customer account; `balance` reverse-derived from ledger |
| `cards` | dim | 7,000 | Issued, expired, reissued — `valid_to` shifts off Feb 29 in non-leap years |
| `merchants` | dim | 200 | Industry, MCC, region |
| `transactions` | fact | 100,000 | Generated in **chronological order** so balances reconcile |
| `loans` | fact | 1,000 | Principal, term, APR, status |
| `loan_payments` | fact | 12,000 | Scheduled and actual repayments |

## Sample command

```bash
synth-datagen fintech \
    --seed 42 \
    --output ./out/fintech \
    --rows customers=500,transactions=5000 \
    --data-quality light \
    --dialect postgres
```

## Schema highlights

- **`transactions` are chronological.** The generator emits them in `created_at` order, so `accounts.balance` after the run equals the running sum of debits/credits up to the cutoff date. This is the only scenario where row order matters for downstream reconciliation tests.
- **`cards.valid_to` leap-day fix.** A card issued on Feb 29 with a 4-year validity used to crash; the generator now shifts `valid_to` forward to March 1 when the +N-year offset would land on a non-existent Feb 29. (Hardened with a regression test in Phase 3.)
- **`accounts.balance`** is reverse-derived from the ledger after generation, so the dim and the fact are always internally consistent.
- **Loan repayments** follow the schedule embedded in `loans` (term × monthly amount). Some loans have missed payments, late payments, or early payoffs depending on `--data-quality`.

## Fraud signals (with `--data-quality medium` or `heavy`)

When data-quality injection is on, transactions get realistic fraud signatures interleaved into the clean ledger:

- Velocity bursts (multiple high-value transactions in seconds)
- Out-of-region merchant + card-region mismatches
- Card-not-present spikes after a long quiet period
- Round-amount clusters that don't match merchant pricing patterns

These aren't labelled — building the labels is your exercise. They are statistically distinguishable from the clean baseline at `--data-quality none`.

## Python API equivalent

```python
from pathlib import Path

from synth_datagen.config import (
    DataQuality, DataQualityConfig, Dialect,
    GeneratorConfig, Scenario, SchemaType,
)
from synth_datagen.pipeline import run_pipeline

config = GeneratorConfig(
    scenario=Scenario.FINTECH,
    schema_type=SchemaType.STAR,
    dialect=Dialect.POSTGRES,
    seed=42,
    output_dir=Path("./out/fintech"),
    row_overrides={"customers": 500, "transactions": 5_000},
    data_quality=DataQualityConfig(level=DataQuality.LIGHT),
)
run_pipeline(config)
```

## Determinism caveat

Because `transactions` are emitted in chronological order, `--seed` controls every value but the row-write order is not arbitrary — re-running with the same seed produces byte-identical CSVs (verified by the determinism test in `tests/test_fintech_realism.py::test_fintech_csv_byte_equality`).
