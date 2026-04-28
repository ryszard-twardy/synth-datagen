from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.kupferkanne_rfm import (
    DIM_CUSTOMERS_EXPORT_COLUMNS,
    DIM_PRODUCTS_EXPORT_COLUMNS,
    ITEMS_COLUMNS,
    ORDERS_COLUMNS,
    build_clean_kupferkanne_frames,
    generate_kupferkanne_rfm,
)
from src.kupferkanne_rfm_config import load_kupferkanne_rfm_config


@pytest.fixture(scope="module")
def generated_dataset(tmp_path_factory):
    config = load_kupferkanne_rfm_config(Path("configs/kupferkanne_rfm_v3.yaml"))
    output_dir = tmp_path_factory.mktemp("kupferkanne_rfm_v3") / "dataset"
    generate_kupferkanne_rfm(config, output_dir, seed=42)
    clean_frames = build_clean_kupferkanne_frames(config, seed=42)
    return output_dir, config, clean_frames


def test_kupferkanne_v3_generation_writes_star_schema_outputs(generated_dataset) -> None:
    output_dir, _config, _clean = generated_dataset
    dimensions_dir = output_dir / "dimensions"
    monthly_dir = output_dir / "monthly"

    orders_files = sorted(path.name for path in monthly_dir.glob("orders20*.csv"))
    items_files = sorted(path.name for path in monthly_dir.glob("items20*.csv"))

    assert len(orders_files) == 39
    assert len(items_files) == 39
    assert orders_files[0] == "orders202301.csv"
    assert orders_files[-1] == "orders202603.csv"
    assert items_files[0] == "items202301.csv"
    assert items_files[-1] == "items202603.csv"
    assert not list(output_dir.glob("sales20*.csv"))
    assert (dimensions_dir / "dim_customers.csv").exists()
    assert (dimensions_dir / "dim_products.csv").exists()

    first_orders = pd.read_csv(monthly_dir / orders_files[0])
    first_items = pd.read_csv(monthly_dir / items_files[0])
    dim_customers = pd.read_csv(dimensions_dir / "dim_customers.csv")
    dim_products = pd.read_csv(dimensions_dir / "dim_products.csv")

    assert list(first_orders.columns) == ORDERS_COLUMNS
    assert list(first_items.columns) == ITEMS_COLUMNS
    assert list(dim_customers.columns) == DIM_CUSTOMERS_EXPORT_COLUMNS
    assert list(dim_products.columns) == DIM_PRODUCTS_EXPORT_COLUMNS
    assert first_items["LineNumber"].dtype.kind in {"i", "u"}
    assert "OrderValue" not in first_orders.columns
    assert "OrderTotal" not in first_orders.columns
    assert "ProductName" not in first_items.columns
    assert "ProductCategory" not in first_items.columns
    assert "UnitCost" not in first_items.columns
    assert "Country" not in first_items.columns

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "4-table-star"
    assert manifest["output"]["dim_customers_columns"] == DIM_CUSTOMERS_EXPORT_COLUMNS
    assert manifest["validation_checks"]["orders_file_count_is_39"] is True
    assert manifest["validation_checks"]["items_file_count_is_39"] is True
    assert manifest["validation_checks"]["dimensions_count_is_2"] is True


def test_kupferkanne_v3_clean_frames_obey_line_item_formula_and_baskets(generated_dataset) -> None:
    _output_dir, _config, clean = generated_dataset
    clean_lines = clean["clean_lines"]
    dim_customers = clean["dim_customers"]
    dim_products = clean["dim_products"]
    fact_orders = clean["fact_orders"]

    assert list(dim_customers.columns) == [
        "CustomerID",
        "signup_date",
        "Country",
        "customer_archetype",
        "churn_end_month",
        "first_name",
        "last_name",
        "email",
        "phone",
        "state",
        "city",
        "address",
    ]
    assert list(dim_products.columns)[:7] == ["ProductID", "ProductName", "ProductCategory", "Brand", "RetailPrice", "UnitCost", "MarginPct"]
    assert list(fact_orders.columns) == ["OrderID", "CustomerID", "OrderDate", "Country", "OrderDiscountPct", "BasketItemCount"]
    assert dim_customers["email"].is_unique
    assert dim_customers[["first_name", "last_name", "email", "phone", "state", "city", "address"]].notna().all().all()

    expected = (
        pd.to_numeric(clean_lines["Quantity"], errors="coerce")
        * pd.to_numeric(clean_lines["UnitPrice"], errors="coerce")
        * (1 - pd.to_numeric(clean_lines["LineDiscountPct"], errors="coerce"))
    ).round(2)
    actual = pd.to_numeric(clean_lines["LineNetAmount"], errors="coerce").round(2)
    assert np.allclose(expected.to_numpy(), actual.to_numpy(), atol=0.01)
    weighted_order_discount = (
        clean_lines.assign(
            gross_line_amount=(
                pd.to_numeric(clean_lines["Quantity"], errors="coerce")
                * pd.to_numeric(clean_lines["UnitPrice"], errors="coerce")
            ),
            discount_value=(
                pd.to_numeric(clean_lines["Quantity"], errors="coerce")
                * pd.to_numeric(clean_lines["UnitPrice"], errors="coerce")
                * pd.to_numeric(clean_lines["LineDiscountPct"], errors="coerce")
            ),
        )
        .groupby("OrderID")[["gross_line_amount", "discount_value"]]
        .sum()
    )
    weighted_order_discount["expected_order_discount"] = (
        weighted_order_discount["discount_value"] / weighted_order_discount["gross_line_amount"]
    ).round(4)
    actual_order_discount = fact_orders.set_index("OrderID")["OrderDiscountPct"].round(4)
    assert np.allclose(actual_order_discount.to_numpy(), weighted_order_discount["expected_order_discount"].to_numpy(), atol=1e-4)

    basket_counts = clean_lines.groupby("OrderID")["OrderLineNumber"].nunique()
    assert fact_orders.set_index("OrderID")["BasketItemCount"].eq(basket_counts).all()
    assert 0.53 <= float((basket_counts == 1).mean()) <= 0.63
    assert float((basket_counts >= 5).mean()) < 0.03
    assert clean_lines[["OrderID", "OrderLineNumber"]].duplicated().sum() == 0

    expected_line_numbers = clean_lines.groupby("OrderID").cumcount() + 1
    assert clean_lines["OrderLineNumber"].tolist() == expected_line_numbers.tolist()
    first_line_numbers = clean_lines.groupby("OrderID")["OrderLineNumber"].first()
    assert first_line_numbers.eq(1).all()
    assert first_line_numbers.loc[basket_counts[basket_counts.eq(1)].index].eq(1).all()


def test_kupferkanne_v3_generation_keeps_required_clusters_and_joins(generated_dataset) -> None:
    output_dir, _config, clean = generated_dataset
    monthly_dir = output_dir / "monthly"
    dimensions_dir = output_dir / "dimensions"

    feb_2024_orders = pd.read_csv(monthly_dir / "orders202402.csv")
    mar_2024_items = pd.read_csv(monthly_dir / "items202403.csv")
    jan_2024_orders = pd.read_csv(monthly_dir / "orders202401.csv")
    dim_customers = pd.read_csv(dimensions_dir / "dim_customers.csv")
    dim_products = pd.read_csv(dimensions_dir / "dim_products.csv")

    malformed = feb_2024_orders["OrderDate"].astype(str).str.contains(r"/|\\.|Feb", regex=True, na=False).sum()
    cents = pd.to_numeric(mar_2024_items["LineNetAmount"], errors="coerce").fillna(0).gt(500).sum()
    future = jan_2024_orders["OrderDate"].astype(str).eq("2027-01-01").sum()

    assert malformed > 0
    assert cents > 0
    assert future > 0

    all_item_frames = [pd.read_csv(path) for path in sorted(monthly_dir.glob("items20*.csv"))]
    all_items = pd.concat(all_item_frames, ignore_index=True)
    duplicate_rows = all_items.duplicated().sum()
    assert duplicate_rows > 0

    orders_lookup = pd.concat(
        [
            pd.read_csv(path).assign(_shard=path.name.replace("orders", "").replace(".csv", ""))
            for path in sorted(monthly_dir.glob("orders20*.csv"))
        ],
        ignore_index=True,
    )
    items_lookup = pd.concat(
        [
            pd.read_csv(path).assign(_shard=path.name.replace("items", "").replace(".csv", ""))
            for path in sorted(monthly_dir.glob("items20*.csv"))
        ],
        ignore_index=True,
    )
    assert set(orders_lookup["CustomerID"].dropna().astype(str).str.strip()) - set(dim_customers["CustomerID"]) == set()
    assert set(items_lookup["ProductID"].dropna().astype(str).str.strip()) - set(dim_products["ProductID"]) == set()
    assert set(items_lookup["OrderID"].dropna().astype(str).str.strip()) - set(orders_lookup["OrderID"].dropna().astype(str).str.strip()) == set()

    clean_lines = clean["clean_lines"]
    advent_rows = clean_lines.loc[clean_lines["ProductID"].isin({"PROD-009", "PROD-018", "PROD-043"})]
    advent_months = pd.to_datetime(advent_rows["OrderDate"]).dt.month.unique().tolist()
    assert sorted(advent_months) == [11, 12]


def test_kupferkanne_v3_manifest_tracks_country_volume_and_brands(generated_dataset) -> None:
    output_dir, config, _clean = generated_dataset
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    dim_products = pd.read_csv(output_dir / "dimensions" / "dim_products.csv")
    country_targets = {item.code: item.share for item in config.countries}

    assert abs(manifest["customer_summary"]["country_distribution"]["DE"] - country_targets["DE"]) <= 0.02
    assert abs(manifest["customer_summary"]["country_distribution"]["AT"] - country_targets["AT"]) <= 0.02
    assert 250000 <= manifest["clean_metrics"]["total_item_rows"] <= 280000
    assert 170000 <= manifest["clean_metrics"]["unique_orders"] <= 185000
    assert 14300 <= manifest["clean_metrics"]["unique_customers"] <= 15700
    assert set(dim_products["Brand"].unique()) == {
        "Kupferkanne Eigenmarke",
        "Terroir Select",
        "Partner Brands",
        "Kupferkanne Geschenke",
        "Artisan Direct",
    }
    assert dim_products["MarginPct"].between(0.20, 0.70).all()


def test_kupferkanne_v3_generation_honors_dim_customer_extra_column_subset(tmp_path) -> None:
    base = yaml.safe_load(Path("configs/kupferkanne_rfm_v3.yaml").read_text(encoding="utf-8"))
    base["period"]["end_date"] = "2023-01-31"
    base["customers"]["target_total_customers"] = 500
    base["validation_targets"]["target_total_orders"] = 700
    base["validation_targets"]["unique_orders_min"] = 600
    base["validation_targets"]["unique_orders_max"] = 800
    base["validation_targets"]["total_rows_min"] = 900
    base["validation_targets"]["total_rows_max"] = 1400
    base["validation_targets"]["unique_customers_target"] = 500
    base["output"]["dim_customers_extra_columns"] = ["first_name", "email", "city"]
    config_path = tmp_path / "kupferkanne_subset.yaml"
    config_path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")

    config = load_kupferkanne_rfm_config(config_path)
    output_dir = tmp_path / "subset_output"
    generate_kupferkanne_rfm(config, output_dir, seed=42)

    dim_customers = pd.read_csv(output_dir / "dimensions" / "dim_customers.csv")
    assert list(dim_customers.columns) == ["CustomerID", "SignupDate", "CustomerArchetype", "FirstName", "Email", "Country", "City"]
