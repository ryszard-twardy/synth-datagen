"""
Audit bad-data injection helpers for monthly retail sales exports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .monthly_sales_profile import (
    MonthlySalesBadDataProfile,
    MonthlySalesNormalizedAuditProfile,
)


def _count_from_rate(total: int, rate: float) -> int:
    if total <= 0 or rate <= 0:
        return 0
    return min(total, max(1, int(round(total * rate))))


def _allocate_counts(total: int, capacities: list[int]) -> list[int]:
    if total <= 0 or not capacities:
        return [0] * len(capacities)
    total_capacity = sum(capacities)
    if total_capacity <= 0:
        return [0] * len(capacities)
    capped_total = min(total, total_capacity)
    weights = np.array(capacities, dtype=float) / float(total_capacity)
    raw = weights * capped_total
    counts = np.floor(raw).astype(int)
    counts = np.minimum(counts, np.array(capacities, dtype=int))
    remaining = int(capped_total - counts.sum())
    if remaining > 0:
        order = np.argsort(-(raw - counts))
        for idx in order.tolist():
            if remaining <= 0:
                break
            if counts[idx] >= capacities[idx]:
                continue
            counts[idx] += 1
            remaining -= 1
    return counts.tolist()


def _inject_normalized_nulls(
    tables: dict[str, pd.DataFrame],
    audit: MonthlySalesNormalizedAuditProfile,
    rng: np.random.Generator,
) -> dict[str, object]:
    targets = [
        ("dim_customers", "city"),
        ("dim_customers", "segment"),
        ("dim_promotions", "promo_name"),
    ]
    capacities = [len(tables[table_name]) for table_name, _ in targets]
    requested = _count_from_rate(sum(capacities), audit.null_required_rate)
    allocations = _allocate_counts(requested, capacities)
    actual = 0
    for (table_name, column_name), count in zip(targets, allocations, strict=False):
        if count <= 0:
            continue
        frame = tables[table_name]
        picks = rng.choice(len(frame), size=count, replace=False)
        frame.loc[picks, column_name] = np.nan
        actual += len(picks)
    return {"actual_count": actual, "requested_count": requested}


def _inject_normalized_negatives(
    tables: dict[str, pd.DataFrame],
    audit: MonthlySalesNormalizedAuditProfile,
    rng: np.random.Generator,
) -> dict[str, object]:
    targets = [
        ("fact_orders", "subtotal"),
        ("fact_orders", "order_total"),
        ("fact_order_items", "qty"),
        ("fact_payments", "amount"),
    ]
    capacities = [len(tables[table_name]) for table_name, _ in targets]
    requested = _count_from_rate(sum(capacities), audit.negative_numeric_rate)
    allocations = _allocate_counts(requested, capacities)
    actual = 0
    for (table_name, column_name), count in zip(targets, allocations, strict=False):
        if count <= 0:
            continue
        frame = tables[table_name]
        picks = rng.choice(len(frame), size=count, replace=False)
        values = pd.to_numeric(frame.loc[picks, column_name], errors="coerce")
        if column_name == "qty":
            frame.loc[picks, column_name] = (
                -values.abs().fillna(1).clip(lower=1).round().astype(int)
            )
        else:
            frame.loc[picks, column_name] = (-values.abs().fillna(1.0)).round(2)
        actual += len(picks)
    return {"actual_count": actual, "requested_count": requested}


def _inject_normalized_outliers(
    tables: dict[str, pd.DataFrame],
    audit: MonthlySalesNormalizedAuditProfile,
    rng: np.random.Generator,
) -> dict[str, object]:
    targets = [
        ("fact_orders", "order_total"),
        ("fact_order_items", "line_total"),
        ("fact_payments", "amount"),
    ]
    capacities = [len(tables[table_name]) for table_name, _ in targets]
    requested = _count_from_rate(sum(capacities), audit.monetary_outlier_rate)
    allocations = _allocate_counts(requested, capacities)
    actual = 0
    for (table_name, column_name), count in zip(targets, allocations, strict=False):
        if count <= 0:
            continue
        frame = tables[table_name]
        picks = rng.choice(len(frame), size=count, replace=False)
        values = (
            pd.to_numeric(frame.loc[picks, column_name], errors="coerce")
            .abs()
            .fillna(25.0)
        )
        multipliers = rng.uniform(12.0, 40.0, size=count)
        frame.loc[picks, column_name] = (values * multipliers).round(2)
        actual += len(picks)
    return {"actual_count": actual, "requested_count": requested}


def apply_monthly_audit_bad_data(
    tables: dict[str, pd.DataFrame],
    audit: MonthlySalesBadDataProfile,
    rng: np.random.Generator,
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    exported = {name: frame.copy(deep=True) for name, frame in tables.items()}
    if not audit.enabled:
        return exported, {}
    summary = {
        "null_required_fields": _inject_normalized_nulls(
            exported, audit.normalized, rng
        ),
        "negative_numeric_values": _inject_normalized_negatives(
            exported, audit.normalized, rng
        ),
        "monetary_outliers": _inject_normalized_outliers(
            exported, audit.normalized, rng
        ),
    }
    return exported, summary


def _format_order_value_variant(value: float, rng: np.random.Generator) -> str:
    style = int(rng.integers(0, 4))
    if style == 0:
        return str(int(round(value * 100)))
    if style == 1:
        return f"USD {value:,.2f}"
    if style == 2:
        return f"{value:,.2f} USD".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def apply_flat_audit_bad_data(
    flat: pd.DataFrame,
    audit: MonthlySalesBadDataProfile,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not audit.enabled:
        return flat.copy(deep=True), {}

    dirty = flat.copy(deep=True)
    summary: dict[str, object] = {}
    original_len = len(dirty)

    duplicate_count = _count_from_rate(original_len, audit.flat.duplicate_orderid_rate)
    if duplicate_count:
        picks = rng.choice(original_len, size=duplicate_count, replace=False)
        dirty = pd.concat([dirty, dirty.iloc[picks].copy(deep=True)], ignore_index=True)
    summary["duplicate_order_ids"] = {
        "actual_count": duplicate_count,
        "requested_count": duplicate_count,
    }

    remaining_defects = {
        "bad_orderdate_formats": _count_from_rate(
            original_len, audit.flat.bad_orderdate_rate
        ),
        "mixed_ordervalue_formats": _count_from_rate(
            original_len, audit.flat.mixed_ordervalue_format_rate
        ),
        "null_required_fields": _count_from_rate(
            original_len, audit.flat.null_required_rate
        ),
        "negative_ordervalue": _count_from_rate(
            original_len, audit.flat.negative_ordervalue_rate
        ),
    }
    row_order = rng.permutation(len(dirty))
    cursor = 0

    bad_dates_count = remaining_defects["bad_orderdate_formats"]
    if bad_dates_count:
        picks = row_order[cursor : cursor + bad_dates_count]
        cursor += bad_dates_count
        variants = np.array(["2026-13-40", "31/02/2026", "not_a_date"], dtype=object)
        dirty.loc[picks, "OrderDate"] = rng.choice(variants, size=len(picks))
    summary["bad_orderdate_formats"] = {
        "actual_count": bad_dates_count,
        "requested_count": bad_dates_count,
    }

    null_count = remaining_defects["null_required_fields"]
    if null_count:
        picks = row_order[cursor : cursor + null_count]
        cursor += null_count
        columns = rng.choice(["CustomerID", "ProductType"], size=len(picks))
        for idx, column_name in zip(picks.tolist(), columns.tolist(), strict=False):
            dirty.at[idx, column_name] = np.nan
    summary["null_required_fields"] = {
        "actual_count": null_count,
        "requested_count": null_count,
    }

    negative_count = remaining_defects["negative_ordervalue"]
    if negative_count:
        picks = row_order[cursor : cursor + negative_count]
        cursor += negative_count
        values = (
            pd.to_numeric(dirty.loc[picks, "OrderValue"], errors="coerce")
            .abs()
            .fillna(1.0)
        )
        dirty.loc[picks, "OrderValue"] = (-values).round(2)
    summary["negative_ordervalue"] = {
        "actual_count": negative_count,
        "requested_count": negative_count,
    }

    mixed_count = remaining_defects["mixed_ordervalue_formats"]
    if mixed_count:
        picks = row_order[cursor : cursor + mixed_count]
        dirty["OrderValue"] = dirty["OrderValue"].astype(object)
        for idx in picks.tolist():
            value = abs(
                float(
                    pd.to_numeric(
                        pd.Series([dirty.at[idx, "OrderValue"]]), errors="coerce"
                    )
                    .fillna(0.0)
                    .iloc[0]
                )
            )
            dirty.at[idx, "OrderValue"] = _format_order_value_variant(
                value if value > 0 else 1.0, rng
            )
    summary["mixed_ordervalue_formats"] = {
        "actual_count": mixed_count,
        "requested_count": mixed_count,
    }

    return dirty, summary
