"""Regression guard for the kupferkanne-rfm vintage-retention artifact (issue #1).

Pre-fix, month-1 (m1) cohort retention collapses by acquisition vintage because
repeat orders are a shared monthly budget sprayed across a growing eligible base
(``kupferkanne_rfm.py:1025`` / ``:1049``). This test asserts the *fixed* property:
once the repeat budget scales with the eligible base, m1 retention is stable across
vintages of the same calendar month (intended seasonal reactivation is preserved,
the spurious calendar-time dilution is not).

The assertion is seasonality-controlled: it groups cohorts by calendar month and
bounds the max-minus-min m1 spread across vintages of that month. A raw cohort-
ordinal trend would wrongly penalise the intended Nov/Dec reactivation banding.

Runs the generator in-memory at a reduced scale (no disk writes); the reduction
preserves the per-month budget/base ratio trajectory, so the artifact still
manifests on pre-fix code.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from synth_datagen.kupferkanne_rfm import build_clean_kupferkanne_frames
from synth_datagen.kupferkanne_rfm_config import (
    KupferkanneRfmConfig,
    load_kupferkanne_rfm_config,
)

# Builds the faker stack + product-probability cache + a multi-thousand-order
# loop, so it exceeds the ~1s fast-lane budget even at reduced scale.
pytestmark = pytest.mark.slow

_V3_CONFIG_PATH = Path("configs/kupferkanne_rfm_v3.yaml")
_SEED = 42

# Reduction factor vs the production v3 config (15000 customers / 175000 orders).
# 10x keeps the budget/base ratio trajectory intact while running fast.
_SCALE_DIVISOR = 10

# Maximum permitted m1 spread (percentage points) across vintages of the same
# calendar month. Pre-fix this is in the tens of points (population dilution);
# the fix must bring every calendar month below this bound.
_MAX_SAME_MONTH_SPREAD_PP = 15.0


def _reduced_config(divisor: int = _SCALE_DIVISOR) -> KupferkanneRfmConfig:
    """Return the v3 config scaled down by ``divisor`` customers and orders.

    Acquisition phases are left untouched: they are relative weights normalised
    by ``_allocate_counts``, so only ``target_total_customers`` and the order
    target need scaling to shrink the run while preserving every distribution.
    """
    base = load_kupferkanne_rfm_config(_V3_CONFIG_PATH)
    data = base.model_dump(mode="json")

    data["customers"]["target_total_customers"] = (
        base.customers.target_total_customers // divisor
    )

    targets = data["validation_targets"]
    targets["target_total_orders"] = (
        base.validation_targets.target_total_orders // divisor
    )
    targets["unique_orders_min"] = base.validation_targets.unique_orders_min // divisor
    targets["unique_orders_max"] = base.validation_targets.unique_orders_max // divisor
    targets["total_rows_min"] = base.validation_targets.total_rows_min // divisor
    targets["total_rows_max"] = base.validation_targets.total_rows_max // divisor
    targets["unique_customers_target"] = (
        base.validation_targets.unique_customers_target // divisor
    )

    return KupferkanneRfmConfig.model_validate(data)


def _cohort_m1_table(
    config: KupferkanneRfmConfig,
) -> pd.DataFrame:
    """Generate clean frames in-memory and return per-vintage m1 retention.

    Columns: cohort (Period[M]), n_customers, m1_pct, base_at_m1 (eligible base
    entering the m1 month). The right-censored tail is excluded.
    """
    clean = build_clean_kupferkanne_frames(config, seed=_SEED)
    fact_orders: pd.DataFrame = clean["fact_orders"]
    dim_customers: pd.DataFrame = clean["dim_customers"]

    order_month = pd.to_datetime(fact_orders["OrderDate"]).dt.to_period("M")
    cust_order_months = (
        pd.DataFrame(
            {"CustomerID": fact_orders["CustomerID"], "order_month": order_month}
        )
        .groupby("CustomerID")["order_month"]
        .apply(set)
    )

    cohorts = pd.to_datetime(dim_customers["signup_date"]).dt.to_period("M")
    dc = pd.DataFrame({"CustomerID": dim_customers["CustomerID"], "cohort": cohorts})

    # Eligible base entering month M = customers signed up before M (every
    # customer places a signup-month order, so signup == first eligibility).
    cohort_sizes = dc["cohort"].value_counts().sort_index()
    cumulative_before = cohort_sizes.cumsum().shift(fill_value=0)

    # Exclude the censored tail: a cohort's m1 month must be strictly before the
    # final (partial) period month. period end 2026-03-15 => drop 2026-02 (m1 in
    # the partial March) and 2026-03 (m1 fully outside the window).
    final_month = pd.Period(config.period.end_date, freq="M")

    rows: list[dict[str, object]] = []
    for cohort, group in dc.groupby("cohort"):
        m1_month = cohort + 1
        if m1_month >= final_month:
            continue
        ids = group["CustomerID"].tolist()
        ordered_m1 = sum(
            1 for cid in ids if m1_month in cust_order_months.get(cid, set())
        )
        rows.append(
            {
                "cohort": cohort,
                "n_customers": len(ids),
                "m1_pct": 100.0 * ordered_m1 / len(ids),
                "base_at_m1": int(cumulative_before.get(cohort, 0)),
            }
        )
    return pd.DataFrame(rows)


def test_kupferkanne_m1_retention_stable_across_vintages() -> None:
    config = _reduced_config()
    table = _cohort_m1_table(config)

    table["cal_month"] = table["cohort"].apply(lambda period: period.month)
    spreads = table.groupby("cal_month")["m1_pct"].agg(lambda s: s.max() - s.min())
    worst_month = int(spreads.idxmax())
    worst_spread = float(spreads.max())

    pearson = float(np.corrcoef(table["base_at_m1"], table["m1_pct"])[0, 1])
    worst_rows = table.loc[table["cal_month"] == worst_month].sort_values("cohort")

    detail = (
        f"scale=1/{_SCALE_DIVISOR} "
        f"(target_total_customers={config.customers.target_total_customers}); "
        f"worst calendar month={worst_month:02d} spread={worst_spread:.1f}pp; "
        f"Pearson(base_at_m1, m1_pct)={pearson:.3f} (diagnostic); "
        f"worst-month m1 by vintage:\n"
        f"{worst_rows[['cohort', 'n_customers', 'm1_pct', 'base_at_m1']].to_string(index=False)}\n"
        f"per-calendar-month spread (pp):\n{spreads.round(1).to_string()}"
    )

    assert worst_spread < _MAX_SAME_MONTH_SPREAD_PP, (
        f"kupferkanne-rfm m1 retention is not stable across vintages. {detail}"
    )
