from __future__ import annotations

import pandas as pd

from synth_datagen.config import Scenario
from tests.helpers import generate_scenario_dfs


def test_retail_order_headers_reconcile_to_items(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.RETAIL, tmp_path)
    orders = dfs["fact_orders"]
    items = dfs["fact_order_items"]
    item_totals = items.groupby("order_id")["line_total"].sum().round(2)
    merged = orders.copy()
    merged["item_total"] = merged["order_id"].map(item_totals).fillna(0.0).round(2)
    assert (merged["subtotal"].round(2) == merged["item_total"]).all()


def test_retail_item_prices_match_catalog(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.RETAIL, tmp_path)
    merged = dfs["fact_order_items"].merge(
        dfs["dim_products"][["product_id", "list_price"]],
        on="product_id",
        how="left",
    )
    assert (merged["unit_price"].round(2) == merged["list_price"].round(2)).all()


def test_retail_temporal_and_status_rules(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.RETAIL, tmp_path)
    orders = dfs["fact_orders"].merge(
        dfs["dim_customers"][["customer_id", "created_at"]].rename(columns={"created_at": "customer_created_at"}),
        on="customer_id",
        how="left",
    )
    assert (pd.to_datetime(orders["created_at"]) >= pd.to_datetime(orders["customer_created_at"])).all()
    cancelled = dfs["fact_payments"].merge(
        dfs["fact_orders"][["order_id", "status"]],
        on="order_id",
        how="left",
    )
    assert not ((cancelled["status_y"] == "cancelled") & (cancelled["status_x"] == "completed")).any()


def test_retail_promotions_and_returns_are_plausible(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.RETAIL, tmp_path)
    bridge = dfs["bridge_order_promotions"]
    assert not bridge.duplicated(["order_id", "promo_id"]).any()

    orders = dfs["fact_orders"][["order_id", "date_id", "status"]]
    promos = dfs["dim_promotions"]
    merged = bridge.merge(orders, on="order_id").merge(promos, on="promo_id")
    order_dates = pd.to_datetime(merged["date_id"].astype(str), format="%Y%m%d")
    assert (order_dates >= pd.to_datetime(merged["valid_from"])).all()
    assert (order_dates <= pd.to_datetime(merged["valid_to"])).all()

    item_status = dfs["fact_order_items"].merge(orders[["order_id", "status"]], on="order_id")
    invalid_returns = item_status["return_flag"] & ~item_status["status"].isin(["delivered", "refunded"])
    assert not invalid_returns.any()

