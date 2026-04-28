from __future__ import annotations

import pandas as pd

from src.config import Scenario
from tests.helpers import generate_scenario_dfs


def test_logistics_inventory_pairs_are_unique(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.LOGISTICS, tmp_path)
    assert not dfs["inventory"].duplicated(["warehouse_id", "product_id"]).any()


def test_logistics_shipment_item_costs_match_products(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.LOGISTICS, tmp_path)
    merged = dfs["shipment_items"].merge(
        dfs["products"][["product_id", "unit_cost"]],
        on="product_id",
        how="left",
        suffixes=("_item", "_product"),
    )
    assert (merged["unit_cost_item"].round(2) == merged["unit_cost_product"].round(2)).all()
    assert (merged["line_value"].round(2) == (merged["qty"] * merged["unit_cost_item"]).round(2)).all()


def test_logistics_transport_and_delivery_are_consistent(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.LOGISTICS, tmp_path)
    merged = dfs["shipments"].merge(
        dfs["carriers"][["carrier_id", "transport"]],
        on="carrier_id",
        how="left",
    )
    assert (merged["transport_mode"] == merged["transport"]).all()
    delivered_mask = merged["delivered_at"].notna()
    assert (
        pd.to_datetime(merged.loc[delivered_mask, "delivered_at"]) >=
        pd.to_datetime(merged.loc[delivered_mask, "shipped_at"])
    ).all()

