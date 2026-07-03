"""Regression guard for issue #7 (final partial month repeat over-allocation).

The monthly order target is scaled by the partial-period day-ratio
(``kupferkanne_rfm.py:390`` ``partial_ratio = active_days / days_in_month``), but the
v0.3.1 per-capita repeat budget
(``kupferkanne_rfm.py:1052`` ``repeat_budget = round(n_eligible_unique *
target_per_capita_repeat_rate * seasonal_mult)``) carries no such term. The final
(partial) simulated month therefore receives a full month's worth of repeat orders.

This test asserts the *fixed* property: the final partial month's repeat volume is
proportional to its active-day fraction, i.e. consistent with the trailing full months
once seasonality and the day-ratio are accounted for. It goes RED on the current
allocator (final-month over-density ~= days_in_month / active_days) and GREEN once
``repeat_budget`` is multiplied by ``active_days / days_in_month`` (Approach A).

Derivation of the metric. Per month M, repeats are derived as ``orders - signups``:
the generation loop appends exactly one signup-month order per new customer and then
``repeat_budget`` repeats on top (``kupferkanne_rfm.py:1005-1083``). For a full month the
realized repeats are ``n_eligible(M) * rate * seasonal_mult(M)``. Define

    Q(M) = repeats(M) * days_in_month(M) / (seasonal_mult(M) * active_days(M))

For a full month ``active_days == days_in_month`` so ``Q(M) == repeats(M) /
seasonal_mult(M) == n_eligible(M) * rate`` -- a season-neutral budget that changes only
with the slowly growing eligible base. After the fix the final partial month's repeats
scale by ``active_days / days_in_month``, so its Q collapses to the same
``n_eligible * rate`` form and matches the trailing full months. Under the defect the
final month keeps a full-month budget, so its Q is inflated by
``days_in_month / active_days``.

Runs the generator in-memory at the canonical 1/5 proof scale (no disk writes), the same
scale and seed as the PR #6 m1-stability regression.
"""

from __future__ import annotations

import calendar
from pathlib import Path

import pandas as pd
import pytest

from synth_datagen.kupferkanne_rfm import build_clean_kupferkanne_frames
from synth_datagen.kupferkanne_rfm_config import (
    KupferkanneRfmConfig,
    load_kupferkanne_rfm_config,
)

# Builds the faker stack + product-probability cache + a multi-thousand-order loop,
# so it exceeds the ~1s fast-lane budget even at reduced scale.
pytestmark = pytest.mark.slow

_V3_CONFIG_PATH = Path("configs/kupferkanne_rfm_v3.yaml")
_SEED = 42

# Reduction factor vs the production v3 config; 1/5 is the canonical proof scale
# (see test_kupferkanne_cohort_retention_stable.py): it preserves the per-month
# budget/base trajectory while staying above binomial sampling noise.
_SCALE_DIVISOR = 5

# Number of trailing full months used as the season-neutral baseline for the final
# month. Kept small so the eligible base of the reference window stays close to the
# final month's base (the base grows over time), minimising growth confounding.
_N_REFERENCE_MONTHS = 3

# Maximum permitted ratio of the final partial month's season-neutral repeat budget Q
# to the trailing full-month mean Q.
#
# The defect leaves the final partial month with a full-month repeat budget, so its Q is
# inflated by days_in_month / active_days (= 31/15 ~= 2.07 for the v3 config's
# 15-of-31-day March 2026). A correctly day-ratio-scaled final month has Q ~= the
# trailing full months' Q, differing only by one to two months of eligible-base growth
# (a few percent) and 1/5-scale sampling noise (~5% on the season-normalised Q across
# Nov-Feb). 1.5 sits roughly midway (log scale) between the corrected ~1.05 and the
# defect's ~2.07: loose enough to tolerate growth + seasonal-normalisation residual +
# seed noise, tight enough that the ~2x over-density cannot pass.
_MAX_FINAL_MONTH_RATIO = 1.5


def _reduced_config(divisor: int = _SCALE_DIVISOR) -> KupferkanneRfmConfig:
    """Return the v3 config scaled down by ``divisor`` customers and orders.

    Only ``target_total_customers`` and the order/validation targets are scaled; the
    period and seasonality are untouched, so the final month stays the partial March
    2026 window that exercises the day-ratio defect.
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


def _monthly_repeat_table(config: KupferkanneRfmConfig) -> pd.DataFrame:
    """Generate clean frames in-memory and return a per-month repeat-budget table.

    Columns (indexed by Period[M]): orders, signups, repeats (= orders - signups),
    active_days, days_in_month, seasonal_mult, q (season-neutral repeat budget).
    """
    clean = build_clean_kupferkanne_frames(config, seed=_SEED)
    fact_orders: pd.DataFrame = clean["fact_orders"]
    dim_customers: pd.DataFrame = clean["dim_customers"]

    orders = pd.to_datetime(fact_orders["OrderDate"]).dt.to_period("M").value_counts()
    signups = (
        pd.to_datetime(dim_customers["signup_date"]).dt.to_period("M").value_counts()
    )
    table = (
        pd.DataFrame({"orders": orders, "signups": signups})
        .fillna(0)
        .astype(int)
        .sort_index()
    )
    # Caveat: repeats are derived as orders minus signups. This is exact for the current
    # generation loop (one signup-month order per new customer, then repeat_budget
    # repeats on top; kupferkanne_rfm.py:1005-1083), but it would silently mismeasure if
    # a future change adds another order source (returns, multi-order signup months).
    # Instrumenting repeat_budget directly is the robust alternative.
    table["repeats"] = table["orders"] - table["signups"]

    baseline = config.seasonality.monthly_order_baseline
    baseline_mean = sum(baseline.values()) / len(baseline)
    period_start = config.period.start_date
    period_end = config.period.end_date

    days_in_month: list[int] = []
    active_days: list[int] = []
    seasonal_mult: list[float] = []
    for period in table.index:
        dim = calendar.monthrange(period.year, period.month)[1]
        active_start = max(period.start_time.date(), period_start)
        active_end = min(period.end_time.date(), period_end)
        days_in_month.append(dim)
        active_days.append((active_end - active_start).days + 1)
        seasonal_mult.append(baseline[period.month] / baseline_mean)

    table["days_in_month"] = days_in_month
    table["active_days"] = active_days
    table["seasonal_mult"] = seasonal_mult
    # Season-neutral, day-ratio-normalised repeat budget. For full months this reduces
    # to repeats / seasonal_mult; the final partial month's Q is inflated by
    # days_in_month / active_days while the defect stands.
    table["q"] = (
        table["repeats"]
        * table["days_in_month"]
        / (table["seasonal_mult"] * table["active_days"])
    )
    return table


def test_final_partial_month_repeats_scale_with_active_days() -> None:
    config = _reduced_config()
    table = _monthly_repeat_table(config)

    final = pd.Period(config.period.end_date, freq="M")
    if final not in table.index:
        pytest.skip(f"final month {final} produced no orders; cannot evaluate")
    final_row = table.loc[final]
    if int(final_row["active_days"]) >= int(final_row["days_in_month"]):
        pytest.skip(
            f"final month {final} is not partial; day-ratio defect cannot arise"
        )

    # Reference = trailing full months, excluding the final partial month and the
    # cold-start first simulation year. The first-year exclusion is symmetric to the
    # PR #6 m1-stability test: the early-sim repeat pool is unstable (tiny eligible base,
    # every member carrying the recency penalty), so it is not a fair budget baseline.
    first_sim_year = pd.Period(config.period.start_date, freq="M").year
    is_full = (table["active_days"] == table["days_in_month"]).to_numpy()
    after_cold_start = table.index.year > first_sim_year
    before_final = table.index < final
    reference = table[is_full & after_cold_start & before_final].iloc[
        -_N_REFERENCE_MONTHS:
    ]
    assert len(reference) == _N_REFERENCE_MONTHS, (
        f"expected {_N_REFERENCE_MONTHS} trailing full reference months, "
        f"got {len(reference)}: {[str(p) for p in reference.index]}"
    )

    reference_q = float(reference["q"].mean())
    final_q = float(final_row["q"])
    ratio = final_q / reference_q
    expected_defect_ratio = int(final_row["days_in_month"]) / int(
        final_row["active_days"]
    )

    detail = (
        f"scale=1/{_SCALE_DIVISOR} seed={_SEED} "
        f"(target_total_customers={config.customers.target_total_customers}); "
        f"final month={final} "
        f"active_days={int(final_row['active_days'])}/"
        f"{int(final_row['days_in_month'])} "
        f"(day-ratio={int(final_row['active_days']) / int(final_row['days_in_month']):.3f}); "
        f"reference full months={[str(p) for p in reference.index]}; "
        f"Q(final)={final_q:.1f} mean Q(reference)={reference_q:.1f} "
        f"ratio={ratio:.3f} (threshold {_MAX_FINAL_MONTH_RATIO}); "
        f"defect predicts ratio ~ days_in_month/active_days = "
        f"{expected_defect_ratio:.3f}\n"
        f"per-month tail:\n"
        f"{table.tail(6)[['repeats', 'active_days', 'days_in_month', 'seasonal_mult', 'q']].round(3).to_string()}"
    )

    assert ratio <= _MAX_FINAL_MONTH_RATIO, (
        "kupferkanne-rfm final partial month is over-allocated repeat orders: its "
        f"season-neutral repeat budget is {ratio:.2f}x the trailing full-month baseline, "
        f"but a day-ratio-scaled final month should be ~1x. {detail}"
    )
