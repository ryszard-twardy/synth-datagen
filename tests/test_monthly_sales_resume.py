from __future__ import annotations

from datetime import date
from pathlib import Path
import pandas as pd
import pytest

from src.id_utils import numeric_suffix
from src.monthly_sales import MonthlyLayout, MonthlySalesConfig, generate_monthly_sales


TABLE_NAMES = [
    "dim_customers",
    "dim_products",
    "dim_stores",
    "dim_date",
    "dim_promotions",
    "fact_orders",
    "fact_order_items",
    "fact_payments",
    "bridge_order_promotions",
]


def _load_tables(root: Path) -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(root / f"{name}.csv") for name in TABLE_NAMES}


def test_monthly_sales_resume_continues_ids_and_preserves_conformed_dimensions(tmp_path) -> None:
    run_a = tmp_path / "run_a"
    config_a = MonthlySalesConfig.from_inputs(
        month="2025-01",
        orders_per_month=12,
        layout=MonthlyLayout.COMBINED,
        include_flat=True,
        output_dir=run_a,
        seed=7,
    )
    outputs_a = generate_monthly_sales(config_a)
    first = _load_tables(outputs_a["combined"])

    run_b = tmp_path / "run_b"
    config_b = MonthlySalesConfig.from_inputs(
        month="2025-02",
        orders_per_month=12,
        layout=MonthlyLayout.BOTH,
        include_flat=True,
        output_dir=run_b,
        seed=7,
        resume_from=outputs_a["combined"],
    )
    outputs_b = generate_monthly_sales(config_b)
    resumed = _load_tables(outputs_b["combined"])

    assert resumed["fact_orders"]["order_id"].is_unique
    assert resumed["fact_order_items"]["item_id"].is_unique
    assert resumed["fact_payments"]["payment_id"].is_unique
    assert set(resumed["dim_customers"]["customer_id"]) == set(first["dim_customers"]["customer_id"])
    assert set(resumed["dim_products"]["product_id"]) == set(first["dim_products"]["product_id"])
    assert set(resumed["dim_stores"]["store_id"]) == set(first["dim_stores"]["store_id"])

    previous_max_order = max(numeric_suffix(value, "order_id") for value in first["fact_orders"]["order_id"])
    new_orders = resumed["fact_orders"].loc[
        ~resumed["fact_orders"]["order_id"].isin(first["fact_orders"]["order_id"]),
        "order_id",
    ]
    assert not new_orders.empty
    assert min(numeric_suffix(value, "order_id") for value in new_orders) > previous_max_order

    month_dirs = sorted(path.name for path in outputs_b["months"].iterdir() if path.is_dir())
    assert month_dirs == ["2025-01", "2025-02"]


def test_monthly_sales_resume_rejects_overlapping_ranges(tmp_path) -> None:
    run_a = tmp_path / "run_overlap_a"
    config_a = MonthlySalesConfig.from_inputs(
        month="2025-01",
        orders_per_month=8,
        layout=MonthlyLayout.COMBINED,
        output_dir=run_a,
        seed=11,
    )
    outputs_a = generate_monthly_sales(config_a)

    with pytest.raises(ValueError):
        generate_monthly_sales(
            MonthlySalesConfig.from_inputs(
                start_date=date(2025, 1, 15),
                end_date=date(2025, 2, 15),
                orders_per_month=8,
                layout=MonthlyLayout.COMBINED,
                output_dir=tmp_path / "run_overlap_b",
                seed=11,
                resume_from=outputs_a["combined"],
            )
        )
