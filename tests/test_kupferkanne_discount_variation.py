from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.kupferkanne_rfm import build_clean_kupferkanne_frames
from src.kupferkanne_rfm_config import KupferkanneRfmConfig


def _small_config() -> KupferkanneRfmConfig:
    base = yaml.safe_load(Path("configs/kupferkanne_rfm_v3.yaml").read_text(encoding="utf-8"))
    base["period"]["end_date"] = "2023-03-31"
    base["customers"]["target_total_customers"] = 600
    base["validation_targets"]["target_total_orders"] = 1200
    base["validation_targets"]["unique_orders_min"] = 1000
    base["validation_targets"]["unique_orders_max"] = 1400
    base["validation_targets"]["total_rows_min"] = 1400
    base["validation_targets"]["total_rows_max"] = 2600
    base["validation_targets"]["unique_customers_target"] = 600
    return KupferkanneRfmConfig.model_validate(base)


def test_kupferkanne_discount_variation_uses_line_level_formula_and_weighted_order_discount() -> None:
    clean = build_clean_kupferkanne_frames(_small_config(), seed=42, discount_variation=True)
    lines = clean["clean_lines"]
    orders = clean["fact_orders"]

    expected = (
        pd.to_numeric(lines["Quantity"], errors="coerce")
        * pd.to_numeric(lines["UnitPrice"], errors="coerce")
        * (1 - pd.to_numeric(lines["LineDiscountPct"], errors="coerce"))
    ).round(2)
    actual = pd.to_numeric(lines["LineNetAmount"], errors="coerce").round(2)
    assert np.allclose(expected.to_numpy(), actual.to_numpy(), atol=0.01)

    weighted = (
        lines.assign(
            gross=(
                pd.to_numeric(lines["Quantity"], errors="coerce")
                * pd.to_numeric(lines["UnitPrice"], errors="coerce")
            ),
            discount_value=(
                pd.to_numeric(lines["Quantity"], errors="coerce")
                * pd.to_numeric(lines["UnitPrice"], errors="coerce")
                * pd.to_numeric(lines["LineDiscountPct"], errors="coerce")
            ),
        )
        .groupby("OrderID")[["gross", "discount_value"]]
        .sum()
    )
    weighted["expected_discount"] = (weighted["discount_value"] / weighted["gross"]).round(4)
    actual_discount = orders.set_index("OrderID")["OrderDiscountPct"].round(4)
    assert np.allclose(actual_discount.to_numpy(), weighted["expected_discount"].to_numpy(), atol=1e-4)


def test_kupferkanne_discount_variation_spreads_margin_by_value_tier() -> None:
    clean = build_clean_kupferkanne_frames(_small_config(), seed=42, discount_variation=True)
    lines = clean["clean_lines"].merge(
        clean["dim_customers"][["CustomerID", "customer_archetype"]],
        on="CustomerID",
        how="left",
    )
    lines["revenue"] = pd.to_numeric(lines["LineNetAmount"], errors="coerce")
    lines["cost"] = pd.to_numeric(lines["Quantity"], errors="coerce") * pd.to_numeric(lines["UnitCost"], errors="coerce")
    margin = (lines.groupby("customer_archetype")[["revenue", "cost"]].sum().pipe(lambda df: (df["revenue"] - df["cost"]) / df["revenue"]))
    high_value_mean = float(margin.loc[["Coffee Regulars", "Premium Enthusiasts", "Power Buyers"]].mean())
    low_value_mean = float(margin.loc[["Gift Buyers", "One-Time Buyers", "New Arrivals"]].mean())
    assert high_value_mean > low_value_mean
