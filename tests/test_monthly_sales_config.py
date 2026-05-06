from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from synth_datagen.monthly_sales import MonthlyLayout, MonthlySalesConfig, build_month_plan
from synth_datagen.monthly_sales_profile import load_monthly_sales_profile


def test_month_input_expands_to_exact_calendar_month(tmp_path) -> None:
    config = MonthlySalesConfig.from_inputs(
        month="2025-02",
        orders_per_month=100,
        layout=MonthlyLayout.COMBINED,
        output_dir=tmp_path / "monthly_cfg",
    )
    assert config.start_date == date(2025, 2, 1)
    assert config.end_date == date(2025, 2, 28)


def test_partial_months_are_prorated_in_plan(tmp_path) -> None:
    config = MonthlySalesConfig.from_inputs(
        start_date=date(2025, 1, 10),
        end_date=date(2025, 3, 5),
        orders_per_month=31,
        layout=MonthlyLayout.COMBINED,
        output_dir=tmp_path / "monthly_cfg",
    )
    plan = build_month_plan(config)
    assert [bucket.label for bucket in plan] == ["2025-01", "2025-02", "2025-03"]
    assert [bucket.order_count for bucket in plan] == [22, 31, 5]
    assert all(bucket.item_count >= bucket.order_count for bucket in plan)


def test_profile_config_builds_growth_plan_with_rises_and_dips(tmp_path) -> None:
    profile_path = Path("configs/monthly_sales.audit_growth_2023_2026.yaml")
    profile = load_monthly_sales_profile(profile_path)
    config = MonthlySalesConfig.from_profile(
        profile,
        profile_path=profile_path,
        output_dir=tmp_path / "monthly_profile",
        seed=42,
    )

    plan = build_month_plan(config)
    counts = [bucket.order_count for bucket in plan]
    deltas = [right - left for left, right in zip(counts, counts[1:], strict=False)]

    assert plan[0].label == "2023-01"
    assert plan[-1].label == "2026-03"
    assert max(counts) <= 5000
    assert counts[-1] > counts[0]
    assert sum(delta > 0 for delta in deltas) >= 3
    assert sum(delta < 0 for delta in deltas) >= 3


def test_sales_files_layout_requires_flat_and_rejects_non_csv_exports(tmp_path) -> None:
    with pytest.raises(ValueError):
        MonthlySalesConfig.from_inputs(
            month="2025-02",
            orders_per_month=100,
            layout=MonthlyLayout.SALES_FILES,
            include_flat=False,
            output_dir=tmp_path / "sales_files_no_flat",
        )

    with pytest.raises(ValueError):
        MonthlySalesConfig.from_inputs(
            month="2025-02",
            orders_per_month=100,
            layout=MonthlyLayout.SALES_FILES,
            output_dir=tmp_path / "sales_files_parquet",
            export_parquet=True,
        )


def test_sales_files_layout_rejects_normalized_audit_defects(tmp_path) -> None:
    with pytest.raises(ValueError):
        MonthlySalesConfig.from_inputs(
            month="2025-02",
            orders_per_month=100,
            layout=MonthlyLayout.SALES_FILES,
            output_dir=tmp_path / "sales_files_audit",
            audit_bad_data={
                "enabled": True,
                "normalized": {"null_required_rate": 0.01},
            },
        )
