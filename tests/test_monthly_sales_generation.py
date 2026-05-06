from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd

from synth_datagen.config import DataQuality
from synth_datagen.monthly_sales import MonthlyLayout, MonthlySalesConfig, generate_monthly_sales
from synth_datagen.monthly_sales_profile import load_monthly_sales_profile


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


def _assert_fk_integrity(tables: dict[str, pd.DataFrame]) -> None:
    assert set(tables["fact_orders"]["customer_id"]).issubset(set(tables["dim_customers"]["customer_id"]))
    assert set(tables["fact_orders"]["store_id"]).issubset(set(tables["dim_stores"]["store_id"]))
    assert set(tables["fact_orders"]["date_id"]).issubset(set(tables["dim_date"]["date_id"]))
    assert set(tables["fact_order_items"]["order_id"]).issubset(set(tables["fact_orders"]["order_id"]))
    assert set(tables["fact_order_items"]["product_id"]).issubset(set(tables["dim_products"]["product_id"]))
    assert set(tables["fact_payments"]["order_id"]).issubset(set(tables["fact_orders"]["order_id"]))
    assert set(tables["bridge_order_promotions"]["order_id"]).issubset(set(tables["fact_orders"]["order_id"]))
    assert set(tables["bridge_order_promotions"]["promo_id"]).issubset(set(tables["dim_promotions"]["promo_id"]))


def _write_audit_profile(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "period:",
                "  start_date: 2025-01-01",
                "  end_date: 2025-04-30",
                "volume:",
                "  max_orders_per_month: 120",
                "  trend_mode: growth",
                "  start_ratio: 0.45",
                "  seasonality_strength: 0.16",
                "  volatility_strength: 0.05",
                "bad_data:",
                "  enabled: true",
                "  normalized:",
                "    null_required_rate: 0.05",
                "    negative_numeric_rate: 0.05",
                "    monetary_outlier_rate: 0.05",
                "  flat:",
                "    duplicate_orderid_rate: 0.05",
                "    bad_orderdate_rate: 0.05",
                "    mixed_ordervalue_format_rate: 0.05",
                "    null_required_rate: 0.05",
                "    negative_ordervalue_rate: 0.05",
                "output:",
                "  layout: both",
                "  include_flat: true",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_sales_files_audit_profile(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "period:",
                "  start_date: 2025-01-01",
                "  end_date: 2025-02-28",
                "volume:",
                "  max_orders_per_month: 80",
                "  trend_mode: growth",
                "  start_ratio: 0.5",
                "  seasonality_strength: 0.1",
                "  volatility_strength: 0.02",
                "bad_data:",
                "  enabled: true",
                "  flat:",
                "    duplicate_orderid_rate: 0.05",
                "    bad_orderdate_rate: 0.05",
                "    mixed_ordervalue_format_rate: 0.05",
                "    null_required_rate: 0.05",
                "    negative_ordervalue_rate: 0.05",
                "output:",
                "  layout: sales-files",
                "  include_flat: true",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_monthly_sales_generation_produces_consistent_combined_and_monthly_outputs(tmp_path) -> None:
    config = MonthlySalesConfig.from_inputs(
        start_date=date(2025, 1, 10),
        end_date=date(2025, 3, 5),
        orders_per_month=30,
        avg_items_per_order=2.4,
        layout=MonthlyLayout.BOTH,
        include_flat=True,
        output_dir=tmp_path / "monthly_sales",
        seed=42,
    )
    outputs = generate_monthly_sales(config)

    combined_tables = _load_tables(outputs["combined"])
    _assert_fk_integrity(combined_tables)
    assert len(combined_tables["fact_payments"]) == len(combined_tables["fact_orders"])
    assert len(combined_tables["fact_order_items"]) >= len(combined_tables["fact_orders"])

    months_root = outputs["months"]
    month_dirs = sorted(path.name for path in months_root.iterdir() if path.is_dir())
    assert month_dirs == ["2025-01", "2025-02", "2025-03"]

    monthly_fact_rows = {"fact_orders": 0, "fact_order_items": 0, "fact_payments": 0, "bridge_order_promotions": 0}
    for month_dir in month_dirs:
        month_tables = _load_tables(months_root / month_dir)
        _assert_fk_integrity(month_tables)
        monthly_fact_rows["fact_orders"] += len(month_tables["fact_orders"])
        monthly_fact_rows["fact_order_items"] += len(month_tables["fact_order_items"])
        monthly_fact_rows["fact_payments"] += len(month_tables["fact_payments"])
        monthly_fact_rows["bridge_order_promotions"] += len(month_tables["bridge_order_promotions"])

        order_months = pd.to_datetime(month_tables["fact_orders"]["created_at"], errors="coerce").dt.strftime("%Y-%m").unique().tolist()
        assert order_months == [month_dir]

    assert len(combined_tables["fact_orders"]) == monthly_fact_rows["fact_orders"]
    assert len(combined_tables["fact_order_items"]) == monthly_fact_rows["fact_order_items"]
    assert len(combined_tables["fact_payments"]) == monthly_fact_rows["fact_payments"]
    assert len(combined_tables["bridge_order_promotions"]) == monthly_fact_rows["bridge_order_promotions"]

    flat = pd.read_csv(outputs["combined"] / "monthly_sales_flat.csv")
    assert len(flat) == len(combined_tables["fact_order_items"])
    flat_totals = flat.groupby("OrderID", as_index=False)["OrderValue"].sum()
    reconciled = flat_totals.merge(
        combined_tables["fact_orders"][["order_id", "order_total"]],
        left_on="OrderID",
        right_on="order_id",
        how="inner",
    )
    assert (reconciled["OrderValue"].round(2) == reconciled["order_total"].round(2)).all()


def test_monthly_sales_light_dq_keeps_ids_and_dates_valid(tmp_path) -> None:
    config = MonthlySalesConfig.from_inputs(
        month="2025-04",
        orders_per_month=25,
        avg_items_per_order=2.0,
        layout=MonthlyLayout.COMBINED,
        include_flat=False,
        output_dir=tmp_path / "monthly_sales_dq",
        seed=99,
        data_quality=DataQuality.LIGHT,
    )
    outputs = generate_monthly_sales(config)
    tables = _load_tables(outputs["combined"])

    assert tables["dim_customers"]["customer_id"].str.fullmatch(r"CU\d{8}").all()
    assert tables["fact_orders"]["order_id"].str.fullmatch(r"OR\d{8}").all()
    assert pd.to_datetime(tables["fact_orders"]["created_at"], errors="coerce").notna().all()
    paid_at = pd.to_datetime(tables["fact_payments"]["paid_at"], errors="coerce")
    assert paid_at[tables["fact_payments"]["paid_at"].notna()].notna().all()
    assert pd.to_datetime(tables["dim_date"]["full_date"], errors="coerce").notna().all()
    _assert_fk_integrity(tables)


def test_monthly_sales_profile_audit_injection_keeps_normalized_tables_structurally_safe(tmp_path) -> None:
    profile_path = _write_audit_profile(tmp_path / "monthly_sales.audit.yaml")
    profile = load_monthly_sales_profile(profile_path)
    config = MonthlySalesConfig.from_profile(
        profile,
        profile_path=profile_path,
        output_dir=tmp_path / "monthly_sales_audit",
        seed=42,
    )

    outputs = generate_monthly_sales(config)
    combined_tables = _load_tables(outputs["combined"])
    _assert_fk_integrity(combined_tables)

    assert combined_tables["dim_customers"]["customer_id"].str.fullmatch(r"CU\d{8}").all()
    assert combined_tables["fact_orders"]["order_id"].str.fullmatch(r"OR\d{8}").all()
    assert pd.to_datetime(combined_tables["fact_orders"]["created_at"], errors="coerce").notna().all()
    assert pd.to_datetime(combined_tables["fact_payments"]["paid_at"], errors="coerce")[combined_tables["fact_payments"]["paid_at"].notna()].notna().all()
    assert pd.to_datetime(combined_tables["dim_date"]["full_date"], errors="coerce").notna().all()
    assert len(combined_tables["fact_payments"]) == len(combined_tables["fact_orders"])
    assert len(combined_tables["fact_order_items"]) >= len(combined_tables["fact_orders"])

    assert combined_tables["dim_customers"]["city"].isna().any() or combined_tables["dim_customers"]["segment"].isna().any()
    assert combined_tables["fact_orders"]["order_total"].lt(0).any() or combined_tables["fact_orders"]["subtotal"].lt(0).any()
    assert (
        combined_tables["fact_orders"]["order_total"].gt(combined_tables["fact_orders"]["order_total"].median() * 8).any()
        or combined_tables["fact_payments"]["amount"].gt(combined_tables["fact_payments"]["amount"].median() * 8).any()
    )

    flat = pd.read_csv(outputs["combined"] / "monthly_sales_flat.csv")
    assert flat["OrderID"].duplicated().any()
    assert pd.to_datetime(flat["OrderDate"], errors="coerce").isna().any()
    assert pd.to_numeric(flat["OrderValue"], errors="coerce").isna().any()
    assert flat["CustomerID"].isna().any() or flat["ProductType"].isna().any()
    numeric_order_values = pd.to_numeric(flat["OrderValue"], errors="coerce")
    assert numeric_order_values.lt(0).any()


def test_sales_files_layout_exports_shared_dimensions_and_monthly_sales_files(tmp_path) -> None:
    config = MonthlySalesConfig.from_inputs(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 31),
        orders_per_month=20,
        layout=MonthlyLayout.SALES_FILES,
        include_flat=True,
        output_dir=tmp_path / "sales_files",
        seed=17,
    )

    outputs = generate_monthly_sales(config)
    root = outputs["sales_files"]

    assert root == config.output_dir
    assert not (root / "months").exists()
    assert not (root / "combined").exists()
    for name in ["dim_customers", "dim_products", "dim_stores", "dim_date", "dim_promotions"]:
        assert (root / f"{name}.csv").exists()
    for name in ["fact_orders.csv", "fact_order_items.csv", "fact_payments.csv", "bridge_order_promotions.csv"]:
        assert not (root / name).exists()

    sales_files = sorted(path.name for path in root.glob("sales_*.csv"))
    assert sales_files == ["sales_202501.csv", "sales_202502.csv", "sales_202503.csv"]

    rows_sum = 0
    for sales_name in sales_files:
        sales_df = pd.read_csv(root / sales_name)
        assert list(sales_df.columns) == ["OrderID", "CustomerID", "OrderDate", "ProductType", "OrderValue", "OrderItemID", "ProductID", "Quantity", "UnitPrice", "Channel"]
        rows_sum += len(sales_df)

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["layout"] == "sales-files"
    assert manifest["sales_files"] == sales_files
    assert sum(manifest["sales_file_row_counts"].values()) == rows_sum


def test_sales_files_layout_can_append_single_month_without_overwriting_dimensions(tmp_path) -> None:
    root = tmp_path / "sales_files_resume"
    first = generate_monthly_sales(
        MonthlySalesConfig.from_inputs(
            month="2025-01",
            orders_per_month=15,
            layout=MonthlyLayout.SALES_FILES,
            include_flat=True,
            output_dir=root,
            seed=23,
        )
    )
    dim_before = pd.read_csv(first["sales_files"] / "dim_customers.csv")

    second = generate_monthly_sales(
        MonthlySalesConfig.from_inputs(
            month="2025-02",
            orders_per_month=15,
            layout=MonthlyLayout.SALES_FILES,
            include_flat=True,
            output_dir=root,
            seed=23,
            resume_from=root,
        )
    )

    dim_after = pd.read_csv(second["sales_files"] / "dim_customers.csv")
    jan = pd.read_csv(root / "sales_202501.csv")
    feb = pd.read_csv(root / "sales_202502.csv")

    assert dim_before.equals(dim_after)
    assert not jan.empty
    assert not feb.empty
    assert (root / "sales_202501.csv").exists()
    assert (root / "sales_202502.csv").exists()
    assert set(jan["OrderID"]).isdisjoint(set(feb["OrderID"]))


def test_sales_files_layout_supports_flat_only_audit_profile(tmp_path) -> None:
    profile_path = _write_sales_files_audit_profile(tmp_path / "sales_files.audit.yaml")
    profile = load_monthly_sales_profile(profile_path)
    config = MonthlySalesConfig.from_profile(
        profile,
        profile_path=profile_path,
        output_dir=tmp_path / "sales_files_audit",
        seed=42,
    )

    outputs = generate_monthly_sales(config)
    sales_file = outputs["sales_files"] / "sales_202501.csv"
    sales_df = pd.read_csv(sales_file)

    assert sales_df["OrderID"].duplicated().any()
    assert pd.to_datetime(sales_df["OrderDate"], errors="coerce").isna().any()
    assert pd.to_numeric(sales_df["OrderValue"], errors="coerce").isna().any()
    assert sales_df["CustomerID"].isna().any() or sales_df["ProductType"].isna().any()
    assert pd.to_numeric(sales_df["OrderValue"], errors="coerce").lt(0).any()
